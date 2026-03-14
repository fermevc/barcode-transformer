# Barcode Transformer

Upload or photograph a barcode (Data Matrix, QR, Code 128, EAN, …) and get back a printable set of individual **Code 128** barcode labels — one per serial number — plus a ready-to-print PDF.

## Features

- Decodes **any common barcode format** from a photo (Data Matrix, QR Code, Code 128, EAN, and more)
- Extracts multiple serial numbers encoded in a single barcode
- Generates individual **Code 128** barcode images for each serial
- Exports a compact **PDF** (up to 40 labels on one A4 page)
- **Camera capture** — use any connected webcam directly in the browser
- Packages as a **single Windows `.exe`** — no Python required on the target machine
- System tray icon with **Open / Quit** actions
- Process exits automatically ~10 s after the browser tab is closed

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Python 3.13 (installed automatically by uv)
- Windows 10/11 (for the compiled exe; the web app runs cross-platform)

## Run in development

```bash
uv run app.py
```

Then open <http://127.0.0.1:5001> in your browser.

## Build a standalone Windows exe

```bash
uv run pyinstaller barcode_transformer.spec
```

The output is `dist/BarcodeTransformer.exe` — a single file that requires no Python installation.
First launch extracts itself to a temp folder (3–5 s), then opens the browser automatically.
A tray icon appears in the taskbar; right-click it to **Open** the browser or **Quit** the app.

## How it works

1. User uploads an image or takes a webcam snapshot
2. **zxing-cpp** attempts to decode all barcodes (with rotation & downscale tries)
3. **pylibdmtx** is used as a fallback for Data Matrix codes
4. **pyzbar** is used as a further fallback for QR / linear codes
5. Decoded text is split on common delimiters (`\n`, `,`, `;`, `|`, `\t`) to extract individual serials
6. Each serial is rendered as a **Code 128** PNG via `python-barcode`
7. Results are displayed in the browser and can be downloaded as a PDF via **ReportLab**

## Project structure

```
app.py                      Flask application
templates/
  index.html                Upload / camera page
  result.html               Results & PDF download page
barcode_transformer.spec    PyInstaller build spec
pyproject.toml              Project metadata & dependencies (managed by uv)
```

## Dependencies

| Package | Purpose |
|---|---|
| `flask` | Web framework |
| `zxing-cpp` | Primary barcode decoder |
| `pylibdmtx` | Data Matrix fallback decoder |
| `pyzbar` | QR / linear barcode fallback decoder |
| `pillow` | Image loading & preprocessing |
| `python-barcode` | Code 128 barcode generation |
| `reportlab` | PDF generation |
| `pystray` | Windows system tray icon |
| `pyinstaller` *(dev)* | Single-file exe packaging |
