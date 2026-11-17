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

# Executáveis windowed não possuem console; Uvicorn/Streamlit consultam isatty.
if sys.platform == 'win32' and getattr(sys, 'frozen', False):
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w', encoding='utf-8')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w', encoding='utf-8')

if sys.platform.startswith("linux"):
    # Qt 6 fornece um Chromium compatível com o frontend do Streamlit atual.
    os.environ.setdefault("QT_API", "pyside6")

import webview
from streamlit_desktop_app import start_desktop_app


APP_TITLE = "MAC Performance"
WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080
API_STARTUP_TIMEOUT_SECONDS = 120


def resource_root() -> Path:
    """Diretório dos arquivos empacotados ou da raiz durante desenvolvimento."""
    bundled = getattr(sys, "_MEIPASS", None)
    return Path(bundled).resolve() if bundled else Path(__file__).resolve().parents[1]


def executable_root() -> Path:
    """Diretório gravável ao lado do executável ou raiz no desenvolvimento."""
    return (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parents[1]
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
    managed = sys.platform == 'win32' and bool(getattr(sys, 'frozen', False))
    if managed:
        from desktop.windows_runtime import installation_file, read_installation, configure_user_paths
        if installation_file().exists():
            state = read_installation()
            if Path(state['install_dir']).resolve() != executable_root():
                raise RuntimeError('Abra o atalho da instalação atual do MAC Performance.')
            environment_file = installation_file().parent / '.env'
            if not environment_file.is_file():
                raise RuntimeError('Configuração ausente. Execute a reparação do instalador.')
        elif not (executable_root() / '.env').is_file():
            raise RuntimeError('Execute MAC-Setup.exe para preparar a instalação.')
        else:
            managed = False  # Compatibilidade explícita com pacote portátil antigo.
            environment_file = executable_root() / '.env'
    else:
        environment_file = executable_root() / ".env"
    load_environment(environment_file, override=True)
    if managed:
        configure_user_paths(state)
    os.environ["MAC_DESKTOP_MODE"] = "1"
    if getattr(sys, "frozen", False) and not managed:
        credentials = executable_root() / "data" / "credentials"
        if not os.environ.get("MAC_GOOGLE_TOKEN_FILE"):
            os.environ["MAC_GOOGLE_TOKEN_FILE"] = str(credentials / "google-drive.json")
        if not os.environ.get("MAC_GOOGLE_DESKTOP_TOKEN_FILE"):
            os.environ["MAC_GOOGLE_DESKTOP_TOKEN_FILE"] = str(credentials / "google-drive-desktop.json")
        if not os.environ.get("MAC_GOOGLE_DESKTOP_REMEMBER_FILE"):
            os.environ["MAC_GOOGLE_DESKTOP_REMEMBER_FILE"] = str(credentials / "desktop-remember.json")
        if not os.environ.get("MAC_GOOGLE_DESKTOP_SESSION_FILE"):
            os.environ["MAC_GOOGLE_DESKTOP_SESSION_FILE"] = str(credentials / "desktop-session.txt")

    bundled_tesseract = root / "tesseract" / (
        "tesseract.exe" if sys.platform == "win32" else "tesseract"
    )
    if managed:
        bundled_tesseract = executable_root() / 'runtime/tesseract/tesseract.exe'
    if bundled_tesseract.is_file():
        os.environ["PATH"] = (
            str(bundled_tesseract.parent)
            + os.pathsep
            + os.environ.get("PATH", "")
        )
        tessdata = bundled_tesseract.parent / 'tessdata' if managed else root / "tessdata"
        if tessdata.is_dir():
            os.environ.setdefault("TESSDATA_PREFIX", str(tessdata))

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    os.chdir(root / 'frontend' / 'streamlit')
    return root / "frontend" / "streamlit" / "app.py"


def find_free_port() -> int:
    """Reserva temporariamente uma porta local livre."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.bind(("127.0.0.1", 0))
        return int(connection.getsockname()[1])


def run_local_api(port: int) -> None:
    """Executa a API no processo filho sem expô-la na rede local."""
    import uvicorn
    from backend.mac_api.main import app

    options = {}
    if sys.platform == 'win32' and os.environ.get('MAC_DESKTOP_MANAGED') == '1':
        from desktop.windows_os import known_directory
        directory = known_directory(False) / 'logs'
        directory.mkdir(parents=True,exist_ok=True)
        options['log_config'] = {
            'version':1,'disable_existing_loggers':False,
            'formatters':{'standard':{'format':'%(asctime)s %(levelname)s %(message)s'}},
            'handlers':{'file':{'class':'logging.handlers.RotatingFileHandler',
                'filename':str(directory/'api.log'),'maxBytes':2_000_000,'backupCount':3,
                'encoding':'utf-8','formatter':'standard'}},
            'loggers':{'uvicorn':{'handlers':['file'],'level':'WARNING','propagate':False},
                       'uvicorn.error':{'handlers':['file'],'level':'WARNING','propagate':False},
                       'backend':{'handlers':['file'],'level':'INFO','propagate':False}},
        }
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        **options,
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
    print(
        f"[MAC Desktop] API local pronta em http://127.0.0.1:{port} "
        f"(health: /health, docs: /docs)",
        flush=True,
    )
    return process, port


def main() -> None:
    windows = sys.platform == 'win32' and bool(getattr(sys, 'frozen', False))
    if windows and '--setup-action' in sys.argv:
        try:
            from desktop import windows_os, windows_runtime
            user = windows_os.known_directory(False)
            user.mkdir(parents=True, exist_ok=True)
            windows_os.protect(user, writers=(windows_os.current_sid(),))
            windows_runtime.configure_logging(user)
            from desktop.windows_setup import main as setup_main
            setup_main(sys.argv[1:])
        except Exception as error:
            from desktop.windows_runtime import show_error
            show_error(error)
            raise SystemExit(1) from None
        return
    bundled = bool(getattr(sys, "frozen", False))
    api_process: multiprocessing.Process | None = None
    instance = None
    original_webview_start = webview.start
    if sys.platform.startswith("linux"):
        # Evita a tentativa ruidosa de carregar GTK antes do backend instalado.
        icon = resource_root() / 'frontend' / 'streamlit' / 'assets' / 'logo_mac.png'
        webview.start = partial(original_webview_start, gui="qt", icon=str(icon))
    try:
        if windows:
            from desktop.windows_os import instance_lock
            instance = instance_lock()
        script = configure_runtime()
        if not script.is_file():
            raise RuntimeError(f"Arquivo principal não encontrado: {script}")
        if windows and os.environ.get('MAC_DESKTOP_MANAGED') == '1':
            from desktop.windows_runtime import prepare
            prepare()
        if bundled:
            api_process, api_port = start_local_api()
            os.environ["MAC_API_BASE_URL"] = f"http://127.0.0.1:{api_port}"
        else:
            api_url = os.environ.get(
                "MAC_API_BASE_URL", "http://127.0.0.1:8000"
            )
            os.environ["MAC_API_BASE_URL"] = api_url
            print(
                f"[MAC Desktop] Usando API externa em {api_url}. "
                "Inicie o backend separadamente antes de abrir a interface.",
                flush=True,
            )
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
    except Exception as error:
        if windows:
            from desktop.windows_runtime import show_error
            show_error(error)
            raise SystemExit(1) from None
        raise
    finally:
        webview.start = original_webview_start
        stop_process(api_process)
        if api_process is not None:
            print("[MAC Desktop] API local encerrada.", flush=True)
        if instance is not None:
            instance.Close()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
