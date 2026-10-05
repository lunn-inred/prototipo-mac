"""Inicializador desktop do MAC Performance usando Streamlit + PyWebView."""

from __future__ import annotations

import multiprocessing
import json
import os
import socket
import sys
import time
from functools import partial
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

if sys.platform.startswith("linux"):
    # Qt 6 fornece um Chromium compatível com o frontend do Streamlit atual.
    os.environ.setdefault("QT_API", "pyside6")

import webview
from streamlit_desktop_app import start_desktop_app


APP_TITLE = "MAC Performance"
WINDOW_WIDTH = 1440
WINDOW_HEIGHT = 900
API_STARTUP_TIMEOUT_SECONDS = 30


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


def load_environment(path: Path, *, override: bool = False) -> None:
    """Carrega configuração externa simples, opcionalmente como fonte principal."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name and override:
            os.environ[name] = value
        elif name:
            os.environ.setdefault(name, value)


def configure_runtime() -> Path:
    root = resource_root()
    # Um único .env configura API e Streamlit. No pacote ele fica ao lado do binário.
    environment_file = executable_root() / ".env"
    load_environment(environment_file, override=True)
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


def find_free_port() -> int:
    """Reserva temporariamente uma porta local livre."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.bind(("127.0.0.1", 0))
        return int(connection.getsockname()[1])


def run_local_api(port: int) -> None:
    """Executa a API no processo filho sem expô-la na rede local."""
    import uvicorn
    from mac_api.main import app

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )


def stop_process(process: multiprocessing.Process | None) -> None:
    if process is None:
        return
    if process.is_alive():
        process.terminate()
    process.join(timeout=5)
    if process.is_alive():
        process.kill()
        process.join(timeout=2)


def wait_for_api(
    port: int,
    process: multiprocessing.Process,
    timeout: float = API_STARTUP_TIMEOUT_SECONDS,
) -> None:
    """Aguarda a API responder ou informa uma falha de inicialização."""
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/health"
    while time.monotonic() < deadline:
        if not process.is_alive():
            raise RuntimeError(
                "A API local foi encerrada durante a inicialização."
            )
        try:
            with urlopen(url, timeout=1) as response:  # noqa: S310 - loopback
                payload = json.loads(response.read().decode("utf-8"))
                if response.status == 200 and payload.get("status") == "ok":
                    return
        except (OSError, URLError, ValueError, json.JSONDecodeError):
            pass
        time.sleep(0.1)
    raise TimeoutError("A API local não iniciou dentro do tempo esperado.")


def start_local_api() -> tuple[multiprocessing.Process, int]:
    port = find_free_port()
    process = multiprocessing.Process(
        target=run_local_api,
        args=(port,),
        name="mac-performance-api",
    )
    process.start()
    try:
        wait_for_api(port, process)
    except Exception:
        stop_process(process)
        raise
    return process, port


def main() -> None:
    script = configure_runtime()
    if not script.is_file():
        raise RuntimeError(f"Arquivo principal não encontrado: {script}")
    api_process: multiprocessing.Process | None = None
    original_webview_start = webview.start
    if sys.platform.startswith("linux"):
        # Evita a tentativa ruidosa de carregar GTK antes do backend instalado.
        webview.start = partial(original_webview_start, gui="qt")
    try:
        api_process, api_port = start_local_api()
        os.environ["MAC_API_BASE_URL"] = f"http://127.0.0.1:{api_port}"
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
        stop_process(api_process)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
