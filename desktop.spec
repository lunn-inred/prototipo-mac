# -*- mode: python ; coding: utf-8 -*-
"""Build multiplataforma do cliente desktop MAC Performance."""

from pathlib import Path
import shutil

from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata


root = Path(SPECPATH).resolve()
datas = [
    (str(root / "app.py"), "."),
    (str(root / "pages"), "pages"),
    (str(root / "assets"), "assets"),
    (str(root / ".streamlit" / "config.toml"), ".streamlit"),
]
binaries = []
hiddenimports = [
    "api_serialization", "athlete_matching", "athlete_service",
    "chart_statistics", "data_filters", "data_repository", "database",
    "gps_data", "gps_extraction", "gps_header", "gps_import_service",
    "gps_import_ui", "jump_crud_ui", "jump_data", "jump_service",
    "legacy_thermography", "player_data", "service_gateway", "settings",
    "thermal_analysis", "thermography_analysis_service",
    "thermography_data", "thermography_service", "ui",
    "mac_api.main", "mac_api.schemas",
]

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
    [str(root / "desktop.py")],
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
