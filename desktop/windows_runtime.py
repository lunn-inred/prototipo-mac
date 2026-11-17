"""Inicialização da instalação Windows, sem Docker ou privilégios administrativos."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import time
from uuid import UUID, uuid4

import psycopg2
from . import windows_os as win


def installation_file():
    return win.known_directory(True) / 'installation.json'


def read_installation():
    path = installation_file()
    if not path.is_file():
        raise RuntimeError('Instalação não preparada. Execute MAC-Setup.exe antes de abrir o aplicativo.')
    state = json.loads(path.read_text(encoding='utf-8'))
    if state.get('format') != 1 or state.get('service') != win.SERVICE or state.get('postgres_major') != 17:
        raise RuntimeError('Configuração de instalação incompatível. Execute a reparação.')
    UUID(state['id'])
    if not isinstance(state.get('port'), int) or not 1024 <= state['port'] <= 65535:
        raise RuntimeError('Porta local inválida.')
    return state


def connection_config(state):
    # Credenciais carregadas do .env protegido pelo instalador, nunca da nuvem.
    return dict(host='127.0.0.1', port=state['port'], dbname='mac_dev',
                user='mac_app', password=os.environ['MAC_LOCAL_DB_PASSWORD'],
                connect_timeout=5, sslmode='disable', application_name='mac_desktop_setup')


def verify_service(state):
    config = win.service_configuration()
    if config is None:
        raise RuntimeError('Serviço PostgreSQL do MAC ausente. Execute a reparação do instalador.')
    command = config[3].casefold()
    binary = str(Path(state['install_dir']) / 'runtime/pgsql/bin/pg_ctl.exe').casefold()
    data = str(win.known_directory(True) / 'postgres').casefold()
    if binary not in command or data not in command:
        raise RuntimeError('O serviço existente não pertence a esta instalação. Nenhum banco será iniciado.')


def backup_database(config, state, *, privileged=False):
    directory = win.known_directory(True) / ('admin/migration-backups' if privileged else 'backups/migrations')
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f'{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex}.dump'
    binary = Path(state['install_dir']) / 'runtime/pgsql/bin'
    environment = dict(os.environ, PGPASSWORD=config['password'], PGOPTIONS='-c default_transaction_read_only=on')
    arguments = ['--host=127.0.0.1', f'--port={config["port"]}', f'--username={config["user"]}', '--dbname=mac_dev']
    win.run_tool([binary / 'pg_dump.exe', *arguments, '--format=custom', '--no-owner', '--no-acl', f'--file={destination}'], env=environment)
    if not destination.is_file() or not destination.stat().st_size:
        raise RuntimeError('Backup prévio vazio; atualização cancelada.')
    win.run_tool([binary / 'pg_restore.exe', '--list', destination])
    checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix('.sha256').write_text(checksum + '\n', encoding='ascii')
    return destination


def configure_user_paths(state):
    common, user = win.known_directory(True), win.known_directory(False)
    user.mkdir(parents=True, exist_ok=True)
    credentials = user / 'credentials'
    credentials.mkdir(exist_ok=True)
    win.protect(user, writers=(win.current_sid(),))
    settings = dict(MAC_DESKTOP_MANAGED='1', MAC_WINDOWS_INSTALLATION_ID=state['id'],
                    MAC_ENVIRONMENT='development', MAC_DB_TARGET='local',
                    MAC_LOCAL_DB_HOST='127.0.0.1', MAC_LOCAL_DB_PORT=str(state['port']),
                    MAC_LOCAL_DB_NAME='mac_dev', MAC_LOCAL_DB_USER='mac_app',
                    MAC_ANALYSES_DIR=str(common / 'thermography'), MAC_BACKUPS_DIR=str(common / 'backups'),
                    MAC_GOOGLE_TOKEN_FILE=str(credentials / 'google-drive.json'),
                    MAC_GOOGLE_DESKTOP_TOKEN_FILE=str(credentials / 'google-drive-desktop.json'),
                    MAC_GOOGLE_DESKTOP_REMEMBER_FILE=str(credentials / 'desktop-remember.json'),
                    MAC_GOOGLE_DESKTOP_SESSION_FILE=str(credentials / 'desktop-session.txt'))
    os.environ.update(settings)
    return user


def configure_logging(user):
    directory = user / 'logs'
    directory.mkdir(exist_ok=True)
    logger = logging.getLogger('mac.desktop')
    if not logger.handlers:
        handler = RotatingFileHandler(directory / 'startup.log', maxBytes=2_000_000, backupCount=3, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(handler); logger.setLevel(logging.INFO)
    return logger


def ensure_database(state, *, initialize=False, privileged=False, progress=lambda value: None):
    from backend.mac_api.core.migrations import run_migrations
    progress('Verificando o serviço do banco...')
    verify_service(state)
    win.start_service()
    config = connection_config(state)
    deadline = time.monotonic() + 60
    while True:
        try:
            with psycopg2.connect(**config) as connection, connection.cursor() as cursor:
                cursor.execute('SHOW server_version_num')
                if int(cursor.fetchone()[0]) // 10000 != 17:
                    raise RuntimeError('PostgreSQL incompatível. A versão principal esperada é 17.')
            break
        except psycopg2.OperationalError:
            if time.monotonic() >= deadline:
                raise RuntimeError('Não foi possível conectar ao banco local. Use a reparação do instalador.') from None
            time.sleep(.3)
    progress('Verificando a estrutura do banco…')
    applied = run_migrations(config, state['id'], initialize=initialize,
                             backup=lambda values: backup_database(values, state, privileged=privileged))
    return applied


@contextmanager
def startup_window():
    """Janela simples e responsiva durante operações bloqueantes, sem WebView."""
    from queue import SimpleQueue
    from threading import Event, Thread
    messages, done = SimpleQueue(), Event()
    def show():
        import win32api, win32con, win32gui
        x = max(0, (win32api.GetSystemMetrics(0) - 440) // 2)
        y = max(0, (win32api.GetSystemMetrics(1) - 110) // 2)
        window = win32gui.CreateWindow('STATIC', 'MAC Performance',
            win32con.WS_VISIBLE | win32con.WS_CAPTION | win32con.WS_POPUP,
            x, y, 440, 110, 0, 0, 0, None)
        label = win32gui.CreateWindow('STATIC', 'Preparando aplicação…',
            win32con.WS_CHILD | win32con.WS_VISIBLE, 20, 20, 400, 35, window, 0, 0, None)
        try:
            while not done.wait(.05):
                while not messages.empty():
                    win32gui.SetWindowText(label, messages.get())
                win32gui.PumpWaitingMessages()
        finally:
            win32gui.DestroyWindow(window)
    thread = Thread(target=show, daemon=True); thread.start()
    try:
        yield messages.put
    finally:
        done.set(); thread.join(timeout=2)


def prepare():
    state = read_installation()
    user = configure_user_paths(state)
    logger = configure_logging(user)
    with startup_window() as progress:
        applied = ensure_database(state, progress=progress)
        logger.info('Inicialização do banco concluída; migrations aplicadas: %d', len(applied))


def show_error(error):
    import ctypes
    import traceback
    # Detalhes técnicos permanecem no log privado, sem expor connection strings.
    reason = str(error) if isinstance(error,RuntimeError) else (getattr(error,'winerror',None) or getattr(error,'pgcode',None))
    frames = ' > '.join(f'{Path(frame.filename).name}:{frame.lineno}:{frame.name}'
                        for frame in traceback.extract_tb(error.__traceback__))
    logging.getLogger('mac.desktop').error('Falha na inicialização: %s (%s); origem: %s',type(error).__name__,reason,frames)
    ctypes.windll.user32.MessageBoxW(None,
        str(error) if isinstance(error, RuntimeError) else 'Não foi possível iniciar. Execute a reparação e consulte os logs em %LOCALAPPDATA%\\MAC Performance\\logs.',
        'MAC Performance — inicialização', 0x10)
