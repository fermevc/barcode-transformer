# barcode_transformer.spec  –  PyInstaller build spec
# Run with:  uv run pyinstaller barcode_transformer.spec

import os
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# Native DLLs bundled inside the Python packages
added_binaries = [
    (
        os.path.join(".venv", "Lib", "site-packages", "pylibdmtx", "libdmtx-64.dll"),
        "pylibdmtx",
    ),
    (
        os.path.join(".venv", "Lib", "site-packages", "pyzbar", "libzbar-64.dll"),
        "pyzbar",
    ),
    (
        os.path.join(".venv", "Lib", "site-packages", "pyzbar", "libiconv.dll"),
        "pyzbar",
    ),
]

added_datas = [
    ("templates", "templates"),           # Flask HTML templates
    *collect_data_files("barcode"),       # fonts & resources used by python-barcode
]

a = Analysis(
    ["app.py"],
    pathex=["."],
    binaries=added_binaries,
    datas=added_datas,
    hiddenimports=[
        "pylibdmtx.pylibdmtx",
        "pyzbar.pyzbar",
        "zxingcpp",
        "barcode.codex",
        "barcode.writer",
        "reportlab.graphics.barcode.code128",
        "pystray",
        "pystray._win32",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="BarcodeTransformer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # set True if UPX is installed and you want a smaller exe
    console=False,       # no console window — it's a web app
    icon=None,
)
