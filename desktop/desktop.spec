# -*- mode: python ; coding: utf-8 -*-
"""Build multiplataforma do cliente desktop MAC Performance."""

from pathlib import Path
import shutil

from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata, collect_submodules


root = Path(SPECPATH).resolve().parent
datas = [
    (str(root / 'frontend/streamlit/app.py'), 'frontend/streamlit'),
    (str(root / 'frontend/streamlit/pages'), 'frontend/streamlit/pages'),
    (str(root / 'frontend/streamlit/assets'), 'frontend/streamlit/assets'),
    (str(root / 'frontend/streamlit/.streamlit/config.toml'), 'frontend/streamlit/.streamlit'),
]
binaries = []
hiddenimports = collect_submodules('backend') + collect_submodules('frontend') + ['desktop.launcher']
hiddenimports = [name for name in hiddenimports if '.tests' not in name]

for package in ("streamlit", "streamlit_drawable_konva"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

for package in ("plotly", "pytesseract", "llama_cloud"):
    datas += collect_data_files(package)

for distribution in ("streamlit", "streamlit-desktop-app"):
    datas += copy_metadata(distribution)

tesseract = shutil.which("tesseract")
if tesseract:
    binaries.append((tesseract, "tesseract"))
    for candidate in (
        Path("/usr/share/tesseract-ocr/5/tessdata"),
        Path("/usr/share/tessdata"),
    ):
        if candidate.is_dir():
            datas.append((str(candidate), "tessdata"))
            break

a = Analysis(
    [str(root / "desktop" / "launcher.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "IPython", "notebook"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MAC Performance",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
