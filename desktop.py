"""Inicializador desktop do MAC Performance usando Streamlit + PyWebView."""

from __future__ import annotations

import multiprocessing
import os
import sys
from functools import partial
from pathlib import Path

if sys.platform.startswith("linux"):
    # Qt 6 fornece um Chromium compatível com o frontend do Streamlit atual.
    os.environ.setdefault("QT_API", "pyside6")

import webview
from streamlit_desktop_app import start_desktop_app


APP_TITLE = "MAC Performance"
WINDOW_WIDTH = 1440
WINDOW_HEIGHT = 900


def resource_root() -> Path:
    """Diretório dos arquivos empacotados ou da raiz durante desenvolvimento."""
    bundled = getattr(sys, "_MEIPASS", None)
    return Path(bundled).resolve() if bundled else Path(__file__).resolve().parent


def executable_root() -> Path:
    """Diretório gravável ao lado do executável ou raiz no desenvolvimento."""
    return (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent
    )


def load_environment(path: Path) -> None:
    """Carrega configuração externa simples sem sobrescrever o ambiente."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name:
            os.environ.setdefault(name, value)


def configure_runtime() -> Path:
    root = resource_root()
    configured_file = os.getenv("MAC_DESKTOP_ENV_FILE")
    environment_file = (
        Path(configured_file).expanduser().resolve()
        if configured_file else executable_root() / "desktop.env"
    )
    load_environment(environment_file)
    os.environ["MAC_DESKTOP_MODE"] = "1"

    bundled_tesseract = root / "tesseract" / (
        "tesseract.exe" if sys.platform == "win32" else "tesseract"
    )
    if bundled_tesseract.is_file():
        os.environ["PATH"] = (
            str(bundled_tesseract.parent)
            + os.pathsep
            + os.environ.get("PATH", "")
        )
        tessdata = root / "tessdata"
        if tessdata.is_dir():
            os.environ.setdefault("TESSDATA_PREFIX", str(tessdata))

    os.chdir(root)
    return root / "app.py"


def main() -> None:
    script = configure_runtime()
    if not script.is_file():
        raise RuntimeError(f"Arquivo principal não encontrado: {script}")
    original_webview_start = webview.start
    if sys.platform.startswith("linux"):
        # Evita a tentativa ruidosa de carregar GTK antes do backend instalado.
        webview.start = partial(original_webview_start, gui="qt")
    try:
        start_desktop_app(
            str(script),
            title=APP_TITLE,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            options={
                "browser.gatherUsageStats": "false",
                "server.fileWatcherType": "none",
                "client.showErrorDetails": "false",
            },
        )
    finally:
        webview.start = original_webview_start


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
