"""Primitivas Windows carregadas sob demanda; importável nos testes Linux."""
import os
from pathlib import Path
import subprocess
import time
from contextlib import contextmanager
import sys

SERVICE = 'MACPerformancePostgreSQL17'
SERVICE_START_TIMEOUT_SECONDS = 180
GROUP = 'MACPerformanceUsers'
MUTEX = r'Global\MACPerformanceDesktop'
SETUP_MUTEX = r'Global\MACPerformanceSetup'


def known_directory(common):
    from win32com.shell import shell, shellcon
    kind = shellcon.CSIDL_COMMON_APPDATA if common else shellcon.CSIDL_LOCAL_APPDATA
    return Path(shell.SHGetFolderPath(0, kind, None, 0)) / 'MAC Performance'


def authorized_group(user):
    import win32net
    import win32security
    # Lookup primeiro: nunca criar grupo ou permissões para um usuário inválido.
    win32security.LookupAccountName(None, user)
    try:
        win32net.NetLocalGroupAdd(None, 1, {'name': GROUP, 'comment': 'Usuários autorizados do MAC Performance'})
    except Exception as error:
        if getattr(error, 'winerror', None) not in (1379, 2223):
            raise
    try:
        win32net.NetLocalGroupAddMembers(None, GROUP, 3, [{'domainandname': user}])
    except Exception as error:
        if getattr(error, 'winerror', None) != 1378:
            raise
    return win32security.ConvertSidToStringSid(win32security.LookupAccountName(None, GROUP)[0])


def current_sid():
    import win32api, win32security, win32con
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        return win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token, win32security.TokenUser)[0])
    finally:
        token.Close()


def protect(path, *, readers=(), writers=()):
    """ACL explícita: Administradores/SYSTEM e somente os SIDs autorizados."""
    import ntsecuritycon, win32security, win32file, win32con
    acl = win32security.ACL()
    flags = 3  # OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE
    grants = {'S-1-5-32-544': ntsecuritycon.FILE_ALL_ACCESS, 'S-1-5-18': ntsecuritycon.FILE_ALL_ACCESS}
    grants.update({sid: ntsecuritycon.FILE_GENERIC_READ | ntsecuritycon.FILE_GENERIC_EXECUTE for sid in readers})
    grants.update({sid: ntsecuritycon.FILE_ALL_ACCESS for sid in writers})
    for sid, mask in grants.items():
        acl.AddAccessAllowedAceEx(win32security.ACL_REVISION, flags, mask, win32security.ConvertStringSidToSid(sid))
    # Trabalhar sobre handle sem seguir junctions no alvo, não conceder ACL ao
    # destino de um link colocado numa pasta de dados por outro processo.
    handle = win32file.CreateFile(str(path),win32con.READ_CONTROL | win32con.WRITE_DAC,
        win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
        None,win32con.OPEN_EXISTING,win32file.FILE_FLAG_OPEN_REPARSE_POINT | win32con.FILE_FLAG_BACKUP_SEMANTICS,None)
    try:
        if win32file.GetFileInformationByHandle(handle)[0] & 0x400:
            raise RuntimeError('Link/junction não permitido nos diretórios privados do aplicativo.')
        win32security.SetSecurityInfo(handle,win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
            None,None,acl,None)
    finally:
        handle.Close()


def run_tool(arguments, *, env=None):
    with external_dlls():
        result = subprocess.run(list(map(str, arguments)), env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=180)
    if result.returncode:
        # Não incluir argumentos/saída de ferramentas: podem conter dados privados.
        raise RuntimeError(f'Falha em {Path(arguments[0]).name} (código {result.returncode}). Consulte o suporte.')
    return result.stdout


@contextmanager
def external_dlls():
    """Evita carregar DLLs do PyInstaller em pg_dump/initdb/sc.exe."""
    import ctypes
    reset = sys.platform == 'win32' and bool(getattr(sys, 'frozen', False))
    if reset:
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    try:
        yield
    finally:
        if reset:
            ctypes.windll.kernel32.SetDllDirectoryW(getattr(sys, '_MEIPASS', None))


def restricted_initdb(arguments):
    """PostgreSQL 17 cria seu próprio token restrito antes de inicializar o cluster.

    O fornecedor também ajusta a DACL do token para o usuário atual. Recriar
    apenas parte desse mecanismo causa DLL_INIT_FAILED em processos elevados.
    Não herdar o marcador que faria initdb pular essa proteção nativa.
    """
    environment = dict(os.environ)
    environment.pop('PG_RESTRICT_EXEC', None)
    return run_tool(arguments, env=environment)


def service_configuration():
    import win32service
    manager = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
    try:
        try:
            service = win32service.OpenService(manager, SERVICE, win32service.SERVICE_QUERY_CONFIG)
        except Exception as error:
            if getattr(error, 'winerror', None) == 1060:
                return None
            raise
        try:
            return win32service.QueryServiceConfig(service)
        finally:
            win32service.CloseServiceHandle(service)
    finally:
        win32service.CloseServiceHandle(manager)


def start_service():
    import win32service
    manager = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
    service = None
    try:
        service = win32service.OpenService(manager, SERVICE, win32service.SERVICE_START | win32service.SERVICE_QUERY_STATUS)
        status = win32service.QueryServiceStatus(service)[1]
        if status == win32service.SERVICE_STOPPED:
            win32service.StartService(service, None)
        deadline = time.monotonic() + SERVICE_START_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            state = win32service.QueryServiceStatus(service)[1]
            if state == win32service.SERVICE_RUNNING:
                return
            if state == win32service.SERVICE_STOPPED:
                raise RuntimeError('O serviço do banco foi interrompido durante a inicialização. Consulte os logs do PostgreSQL.')
            time.sleep(.2)
        raise RuntimeError('O serviço do banco não iniciou. Use a reparação do instalador.')
    finally:
        if service is not None:
            win32service.CloseServiceHandle(service)
        win32service.CloseServiceHandle(manager)


def grant_service_start(group_sid):
    import win32service, win32security, win32con
    manager = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
    service = win32service.OpenService(manager, SERVICE, win32con.READ_CONTROL | win32con.WRITE_DAC)
    try:
        descriptor = win32service.QueryServiceObjectSecurity(service, win32security.DACL_SECURITY_INFORMATION)
        acl = descriptor.GetSecurityDescriptorDacl()
        mask = win32service.SERVICE_QUERY_CONFIG | win32service.SERVICE_QUERY_STATUS | win32service.SERVICE_START | win32con.READ_CONTROL
        acl.AddAccessAllowedAce(win32security.ACL_REVISION, mask, win32security.ConvertStringSidToSid(group_sid))
        descriptor.SetSecurityDescriptorDacl(1, acl, 0)
        win32service.SetServiceObjectSecurity(service, win32security.DACL_SECURITY_INFORMATION, descriptor)
    finally:
        win32service.CloseServiceHandle(service); win32service.CloseServiceHandle(manager)


def instance_lock():
    import win32api, win32event, win32con
    try:
        setup = win32event.OpenMutex(win32con.SYNCHRONIZE,False,SETUP_MUTEX)
    except Exception as error:
        if getattr(error,'winerror',None) != 2:
            raise RuntimeError('A instalação/atualização está em andamento ou bloqueada. Aguarde sua conclusão.') from None
    else:
        setup.Close()
        raise RuntimeError('Aguarde a conclusão do instalador antes de abrir o aplicativo.')
    handle = win32event.CreateMutex(None, False, MUTEX)
    if win32api.GetLastError() == 183:
        handle.Close()
        raise RuntimeError('O MAC Performance já está aberto neste computador.')
    return handle
