from __future__ import annotations

import base64
import io
import os
import re
import sys

import zxingcpp  # type: ignore[import-untyped]
import barcode
from barcode.writer import ImageWriter
from flask import Flask, redirect, render_template, request, send_file, session
from PIL import Image, ImageOps
from pylibdmtx.pylibdmtx import decode as dmtx_decode
from pyzbar.pyzbar import decode as zbar_decode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

import threading

# When running as a PyInstaller bundle the files live under sys._MEIPASS
_BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

# reset by the /heartbeat route; watched by the idle-shutdown thread
_heartbeat_event = threading.Event()
_heartbeat_event.set()

app = Flask(__name__, template_folder=os.path.join(_BASE_DIR, "templates"))
app.secret_key = "barcode-transformer-dev-key"
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB


# ---------------------------------------------------------------------------
# Barcode decoding
# ---------------------------------------------------------------------------

# pylibdmtx timeout per attempt in milliseconds
_DMTX_TIMEOUT_MS = 3_000


def decode_image(img: Image.Image) -> tuple[list[str], list[str]]:
    """
    Decode all barcodes in *img*.

    Tries in order:
      1. zxingcpp  — handles rotation/downscale/inversion internally, widest format support
      2. pylibdmtx — dedicated Data Matrix fallback
      3. pyzbar    — QR / linear codes fallback

    Returns (results, errors).
    """
    seen: set[str] = set()
    results: list[str] = []
    errors: list[str] = []

    def _add(text: str) -> None:
        text = text.strip()
        if text and text not in seen:
            seen.add(text)
            results.append(text)

    # --- 1. zxingcpp (primary) ---
    try:
        found = zxingcpp.read_barcodes(img, try_rotate=True, try_downscale=True, try_invert=True)
        print(f"  zxingcpp {img.size}: {len(found)} result(s)")
        for r in found:
            print(f"    format={r.format}  text={r.text[:80]!r}")
            _add(r.text)
    except Exception as exc:
        errors.append(f"zxingcpp: {exc}")
        print(f"  zxingcpp ERROR: {exc}")

    if results:
        return results, errors

    # --- 2. pylibdmtx fallback (grayscale, two scales) ---
    gray = ImageOps.grayscale(img)
    for label, g in [("full", gray), ("half", gray.reduce(2))]:
        try:
            found = dmtx_decode(g, timeout=_DMTX_TIMEOUT_MS)
            print(f"  dmtx {label} {g.size}: {len(found)} result(s)")
            for obj in found:
                _add(obj.data.decode("utf-8", errors="replace"))
        except Exception as exc:
            errors.append(f"pylibdmtx/{label}: {exc}")
            print(f"  dmtx {label} ERROR: {exc}")

    if results:
        return results, errors

    # --- 3. pyzbar fallback ---
    try:
        found = zbar_decode(gray)
        print(f"  pyzbar {gray.size}: {len(found)} result(s)")
        for obj in found:
            _add(obj.data.decode("utf-8", errors="replace"))
    except Exception as exc:
        errors.append(f"pyzbar: {exc}")
        print(f"  pyzbar ERROR: {exc}")

    return results, errors


# ---------------------------------------------------------------------------
# Serial number parsing
# ---------------------------------------------------------------------------

_DELIMITER = re.compile(r"[\r\n,;|\t]+")


def parse_serials(raw_texts: list[str]) -> list[str]:
    """
    Extract individual serial numbers from decoded barcode text.

    If a single decoded string contains delimiters it is split into tokens.
    Tokens shorter than 3 characters are discarded as noise.
    """
    seen: set[str] = set()
    serials: list[str] = []
    for text in raw_texts:
        for token in _DELIMITER.split(text):
            token = token.strip()
            if len(token) >= 3 and token not in seen:
                seen.add(token)
                serials.append(token)
    return serials


# ---------------------------------------------------------------------------
# Code 128 barcode image generation
# ---------------------------------------------------------------------------

_BARCODE_OPTIONS: dict = {
    "module_width": 0.4,
    "module_height": 15.0,
    "font_size": 8,
    "text_distance": 5.0,
    "quiet_zone": 6.5,
    "dpi": 200,
    "write_text": True,
}


def serial_to_png(serial: str) -> bytes:
    buf = io.BytesIO()
    barcode.get("code128", serial, writer=ImageWriter()).write(buf, options=_BARCODE_OPTIONS)
    buf.seek(0)
    return buf.read()


def serial_to_b64(serial: str) -> str:
    return "data:image/png;base64," + base64.b64encode(serial_to_png(serial)).decode()


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

def build_pdf(serials: list[str]) -> io.BytesIO:
    buf = io.BytesIO()
    page_w, page_h = A4
    margin = 0.8 * cm

    # pick column count so everything fits on one page when possible
    n = len(serials)
    cols = 4 if n > 12 else (3 if n > 6 else 2)
    col_w = (page_w - 2 * margin) / cols

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
    )

    label_style = ParagraphStyle(
        "label", fontSize=6, alignment=1, leading=7, spaceAfter=0
    )

    rows: list[list] = []
    row: list = []

    for serial in serials:
        png_bytes = serial_to_png(serial)
        rl_img = RLImage(io.BytesIO(png_bytes), width=col_w - 0.2 * cm, height=1.1 * cm)
        row.append([rl_img, Paragraph(serial, label_style)])
        if len(row) == cols:
            rows.append(row)
            row = []

    if row:
        row += [""] * (cols - len(row))   # pad last row
        rows.append(row)

    table = Table(rows, colWidths=[col_w] * cols)
    table.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.lightgrey),
    ]))

    doc.build([table])
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return render_template("index.html")


@app.post("/upload")
def upload():
    file = request.files.get("image")
    if not file or not file.filename:
        return render_template("index.html", error="No file selected.")

    try:
        img = Image.open(file.stream)
        img.load()
        img = ImageOps.exif_transpose(img)  # honour EXIF rotation tag
    except Exception:
        return render_template("index.html", error="Could not open the image — please try again.")

    print(f"Loaded image: {img.size} {img.mode}")

    raw, decode_errors = decode_image(img)
    if not raw:
        detail = f" ({decode_errors[0]})" if decode_errors else ""
        return render_template(
            "index.html",
            error=f"No barcodes detected. Try a sharper, better-lit photo.{detail}",
        )

    serials = parse_serials(raw)
    if not serials:
        return render_template(
            "index.html",
            error=f"Barcode decoded but no serials could be parsed. Raw content: {raw[0][:120]}",
        )

    session["serials"] = serials

    items = [{"serial": s, "image": serial_to_b64(s)} for s in serials]
    return render_template("result.html", items=items, count=len(serials))


@app.post("/debug")
def debug():
    """Return the first preprocessed variant as a PNG so you can see what the decoder receives."""
    file = request.files.get("image")
    if not file:
        return "no file", 400
    img = ImageOps.exif_transpose(Image.open(file.stream))
    variant = ImageOps.grayscale(img)
    buf = io.BytesIO()
    variant.save(buf, format="PNG")
    buf.seek(0)
    print(f"Debug: original={img.size} grayscale={variant.size}")
    return send_file(buf, mimetype="image/png")


@app.get("/download-pdf")
def download_pdf():
    serials: list[str] = session.get("serials", [])
    if not serials:
        return redirect("/")

    pdf = build_pdf(serials)
    return send_file(pdf, mimetype="application/pdf", as_attachment=True, download_name="barcodes.pdf")


@app.post("/heartbeat")
def heartbeat():
    """Called by the browser every few seconds; resets the idle shutdown timer."""
    _heartbeat_event.set()
    return "", 204


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _make_tray_icon(port: int):
    """Return a pystray Icon that lives in the system tray."""
    import pystray
    from PIL import Image as PILImage, ImageDraw

    # Draw a simple 64×64 barcode-ish icon
    size = 64
    img = PILImage.new("RGB", (size, size), "#3b82f6")
    draw = ImageDraw.Draw(img)
    for x, w in [(8,4),(14,6),(22,3),(27,8),(37,4),(43,6),(51,3),(56,5)]:
        draw.rectangle([x, 12, x + w, 52], fill="white")

    def on_open(_icon, _item):
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{port}")

    def on_quit(_icon, _item):
        _icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Open", on_open, default=True),
        pystray.MenuItem("Quit", on_quit),
    )
    return pystray.Icon("BarcodeTransformer", img, "Barcode Transformer", menu)


def _idle_watchdog(timeout: int = 10):
    """Shut down if no heartbeat is received for *timeout* seconds."""
    while True:
        fired = _heartbeat_event.wait(timeout=timeout)
        if not fired:
            # timeout elapsed with no heartbeat → browser is gone
            os._exit(0)
        _heartbeat_event.clear()


if __name__ == "__main__":
    import webbrowser

    port = 5001
    frozen = getattr(sys, "frozen", False)

    if frozen:
        # start the idle watchdog only in the packaged exe
        _heartbeat_event = threading.Event()
        _heartbeat_event.set()   # treat startup as first heartbeat
        wd = threading.Thread(target=_idle_watchdog, daemon=True)
        wd.start()

        # open browser after Flask is ready
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()

        # run Flask in background, tray icon on main thread (required by pystray)
        flask_thread = threading.Thread(
            target=lambda: app.run(debug=False, use_reloader=False, port=port),
            daemon=True,
        )
        flask_thread.start()

        tray = _make_tray_icon(port)
        tray.run()          # blocks until user clicks Quit
        os._exit(0)
    else:
        # dev mode — plain run, no tray, no watchdog
        _heartbeat_event = threading.Event()
        app.run(debug=True, use_reloader=True, port=port)
