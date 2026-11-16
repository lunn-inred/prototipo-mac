"""Ações elevadas chamadas exclusivamente pelo instalador Windows.

Sem exportação de nuvem e sem adoção de bancos do desenvolvimento. Dados nunca
são excluídos na reparação ou desinstalação.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from uuid import uuid4

import psycopg2
from psycopg2 import sql
from . import windows_os as win
from .windows_runtime import installation_file, read_installation, verify_service, ensure_database


def write_json(path, value):
    temporary = path.with_suffix('.new')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temporary.replace(path)


def choose_port():
    for port in range(55434, 55445):
        with socket.socket() as listener:
            try:
                listener.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    raise RuntimeError('Nenhuma porta local disponível para o banco do MAC.')


def stop_owned_service(*, unregister=False):
    import win32service, win32con
    if not installation_file().exists():
        if win.service_configuration() is not None:
            raise RuntimeError('Existe um serviço MAC sem identificação. Nenhuma alteração foi realizada.')
        return
    state = read_installation()
    if win.service_configuration() is None:
        return
    verify_service(state)
    if not unregister and state.get('status') == 'ready':
        from dotenv import dotenv_values
        from .windows_runtime import backup_database
        values = dotenv_values(installation_file().parent / '.env')
        win.start_service()
        backup_database(dict(port=state['port'],user='mac_app',password=values['MAC_LOCAL_DB_PASSWORD']),state,privileged=True)
    manager = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
    service = win32service.OpenService(manager, win.SERVICE,
        win32service.SERVICE_STOP | win32service.SERVICE_QUERY_STATUS | win32con.DELETE)
    try:
        status = win32service.QueryServiceStatus(service)[1]
        if status not in (win32service.SERVICE_STOPPED, win32service.SERVICE_STOP_PENDING):
            win32service.ControlService(service, win32service.SERVICE_CONTROL_STOP)
        deadline = time.monotonic() + 90
        while win32service.QueryServiceStatus(service)[1] != win32service.SERVICE_STOPPED:
            if time.monotonic() > deadline:
                raise RuntimeError('O banco não encerrou. A atualização foi cancelada; não force o encerramento.')
            time.sleep(.3)
        if unregister:
            win32service.DeleteService(service)
    finally:
        win32service.CloseServiceHandle(service); win32service.CloseServiceHandle(manager)


def provision_database(state, admin):
    config = dict(host='127.0.0.1', port=state['port'], user='mac_bootstrap',
                  password=admin['admin_password'], dbname='postgres', connect_timeout=5, sslmode='disable')
    connection = psycopg2.connect(**config)
    try:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname='mac_app'")
            if cursor.fetchone() is None:
                cursor.execute(sql.SQL('CREATE ROLE mac_app LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE').format(sql.Literal(admin['app_password'])))
            cursor.execute("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='mac_dev'")
            owner = cursor.fetchone()
            if owner is None:
                cursor.execute('CREATE DATABASE mac_dev OWNER mac_app TEMPLATE template0 ENCODING \'UTF8\'')
            elif owner[0] != 'mac_app':
                raise RuntimeError('Banco local com outro proprietário. Nenhum dado será substituído.')
    finally:
        connection.close()


def install(install_dir, user):
    import win32security
    from dotenv import dotenv_values
    common = win.known_directory(True)
    state_path = installation_file()
    existing = state_path.exists()
    if existing:
        state = read_installation()
        if win.service_configuration() is not None:
            verify_service(state)
    else:
        if common.exists() and any(common.iterdir()):
            raise RuntimeError('Há arquivos de uma instalação não identificada. A pasta foi preservada; solicite revisão.')
        if win.service_configuration() is not None:
            raise RuntimeError('O nome do serviço já está ocupado. Instalação cancelada.')
        state = dict(format=1,id=str(uuid4()),service=win.SERVICE,postgres_major=17,
                     port=choose_port(),install_dir=str(install_dir),status='initializing')
    group = win.authorized_group(user)
    user_sid = win32security.ConvertSidToStringSid(win32security.LookupAccountName(None,user)[0])
    common.mkdir(parents=True,exist_ok=True)
    win.protect(common,readers=(group,user_sid,'S-1-5-19'))
    for name in ('thermography','backups'):
        path = common / name; path.mkdir(exist_ok=True)
        win.protect(path,writers=(group,user_sid))
    private = common / 'admin'; private.mkdir(exist_ok=True); win.protect(private)
    secret_path = private / 'postgres.json'
    if existing:
        if not secret_path.is_file():
            raise RuntimeError('Credenciais administrativas ausentes. O banco não será recriado.')
        admin = json.loads(secret_path.read_text(encoding='utf-8'))
    else:
        admin = dict(admin_password=secrets.token_urlsafe(48),app_password=secrets.token_urlsafe(48),api_key=secrets.token_urlsafe(48))
        write_json(secret_path,admin)
    # Marcador antes de initdb: permite reparar interrupções sem trocar senhas.
    if not existing:
        write_json(state_path,state)
    binary = install_dir / 'runtime/pgsql/bin'
    win.protect(binary.parent,readers=(group,user_sid,'S-1-5-19'))
    version = win.run_tool([binary / 'pg_ctl.exe','--version']).decode('utf-8',errors='replace')
    if 'PostgreSQL) 17.' not in version:
        raise RuntimeError('O pacote deve conter PostgreSQL 17 x64.')
    data = common / 'postgres'
    if not (data / 'PG_VERSION').is_file():
        if existing and state['status'] == 'ready':
            raise RuntimeError('Dados do banco ausentes. Não será criado um banco vazio no lugar; restaure seu backup.')
        data.mkdir(exist_ok=True)
        if any(data.iterdir()):
            raise RuntimeError('Inicialização anterior incompleta. A pasta foi preservada para revisão.')
        win.protect(data,writers=(win.current_sid(),'S-1-5-19'))
        password_file = private / 'initdb-password.tmp'
        win.protect(private,readers=(win.current_sid(),))
        password_file.write_text(admin['admin_password'],encoding='ascii')
        win.protect(password_file,readers=(win.current_sid(),))
        try:
            win.restricted_initdb([binary / 'initdb.exe','-D',data,'-U','mac_bootstrap',
                f'--pwfile={password_file}','--auth=scram-sha-256','--encoding=UTF8','--locale=C'])
        finally:
            password_file.unlink(missing_ok=True)
            win.protect(private)
        win.protect(data,writers=('S-1-5-19',))
    elif (data / 'PG_VERSION').read_text().strip() != '17':
        raise RuntimeError('Versão principal do PostgreSQL incompatível. É necessária uma atualização planejada.')
    include = "include_if_exists = 'mac-performance.conf'"
    if include not in (data / 'postgresql.conf').read_text(encoding='utf-8'):
        with (data / 'postgresql.conf').open('a',encoding='utf-8') as output:
            output.write('\n'+include+'\n')
    (data / 'mac-performance.conf').write_text(
        f"listen_addresses='127.0.0.1'\nport={state['port']}\npassword_encryption='scram-sha-256'\nlogging_collector=on\nlog_directory='log'\nlog_filename='postgresql-%Y-%m-%d.log'\nlog_rotation_age='1d'\nlog_statement='none'\nlog_min_error_statement='panic'\n",encoding='utf-8')
    if existing and Path(state['install_dir']) != install_dir and win.service_configuration() is not None:
        stop_owned_service(unregister=True)
    state['install_dir'] = str(install_dir)
    write_json(state_path,state)
    if win.service_configuration() is None:
        # SCM exige o nome canônico, mesmo no Windows em português.
        win.run_tool([binary / 'pg_ctl.exe','register','-D',data,'-N',win.SERVICE,'-U',r'NT AUTHORITY\LocalService','-S','auto','-t',str(win.SERVICE_START_TIMEOUT_SECONDS)])
    # Repara também uma preparação interrompida com nome localizado da conta.
    command = subprocess.list2cmdline([str(binary/'pg_ctl.exe'),'runservice','-N',win.SERVICE,
                                      '-D',str(data),'-w','-t',str(win.SERVICE_START_TIMEOUT_SECONDS)])
    win.run_tool(['sc.exe','config',win.SERVICE,'obj=',r'NT AUTHORITY\LocalService','binPath=',command])
    win.grant_service_start(group)
    win.grant_service_start(user_sid)
    win.run_tool(['sc.exe','failure',win.SERVICE,'reset=','86400','actions=','restart/5000/restart/15000/restart/60000'])
    win.start_service()
    provision_database(state,admin)
    environment_path = common / '.env'
    values = dict(dotenv_values(environment_path)) if environment_path.exists() else {}
    # Somente parâmetros públicos do cliente OAuth; nunca tokens/senhas do desenvolvedor.
    deployment = install_dir / 'deployment.json'
    if deployment.exists():
        public = json.loads(deployment.read_text(encoding='utf-8-sig'))
        allowed = {'MAC_GOOGLE_ALLOWED_EMAIL','MAC_GOOGLE_DESKTOP_CLIENT_ID','MAC_GOOGLE_DESKTOP_CLIENT_SECRET','MAC_GOOGLE_BACKUP_FOLDER_ID'}
        if set(public)-allowed or any(not isinstance(v,str) or any(ch in v for ch in '\r\n\x00') for v in public.values()):
            raise RuntimeError('Configuração de distribuição inválida.')
        values.update(public)
    if values.get('MAC_GOOGLE_DESKTOP_CLIENT_ID') or values.get('MAC_GOOGLE_DESKTOP_CLIENT_SECRET'):
        required = ('MAC_GOOGLE_DESKTOP_CLIENT_ID','MAC_GOOGLE_DESKTOP_CLIENT_SECRET','MAC_GOOGLE_ALLOWED_EMAIL','MAC_GOOGLE_BACKUP_FOLDER_ID')
        if any(not values.get(name,'').strip() for name in required):
            raise RuntimeError('Configuração Desktop do Google exige ID, secret, conta autorizada e pasta da equipe.')
    values.update(MAC_API_KEY=admin['api_key'],MAC_LOCAL_DB_PASSWORD=admin['app_password'],
        MAC_ENVIRONMENT='development',MAC_DB_TARGET='local',MAC_LOCAL_DB_HOST='127.0.0.1',
        MAC_LOCAL_DB_PORT=str(state['port']),MAC_LOCAL_DB_NAME='mac_dev',MAC_LOCAL_DB_USER='mac_app',
        MAC_ANALYSES_DIR=(common/'thermography').as_posix(),MAC_BACKUPS_DIR=(common/'backups').as_posix())
    environment_path.write_text(''.join(f'{name}={value}\n' for name,value in values.items() if value is not None),encoding='utf-8')
    win.protect(environment_path,readers=(group,user_sid))
    os.environ.update({k:str(v) for k,v in values.items() if v is not None})
    ensure_database(state,initialize=True,privileged=True)
    state['status']='ready';write_json(state_path,state)


def main(arguments):
    if sys.platform != 'win32' or not ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError('A preparação deve ser executada pelo instalador Windows como administrador.')
    parser=argparse.ArgumentParser()
    parser.add_argument('--setup-action',choices=('install','stop','uninstall-service'),required=True)
    parser.add_argument('--authorized-user')
    options=parser.parse_args(arguments)
    if options.setup_action=='install':
        if not options.authorized_user:
            raise RuntimeError('Informe o usuário Windows autorizado.')
        install(Path(sys.executable).resolve().parent,options.authorized_user)
    else:
        stop_owned_service(unregister=options.setup_action=='uninstall-service')
