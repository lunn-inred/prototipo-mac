"""Uma tarefa por vez; polling não depende do timeout de uma requisição longa."""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from uuid import uuid4
import logging
import traceback
import httpx
import psycopg2
from fastapi import HTTPException
from . import service

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='mac-backup')
_lock = Lock()
_jobs = {}


def _failure_detail(error, kind, stage):
    operation = 'sincronização' if kind == 'sync' else 'backup/restauração'
    if isinstance(error, HTTPException):
        return error.detail
    if isinstance(error, ValueError):
        return str(error)
    if isinstance(error, httpx.TimeoutException):
        reason = 'Tempo limite ao acessar o Google Drive. Confira a conexão do backend com o Google.'
    elif isinstance(error, httpx.RequestError):
        reason = 'Falha de conexão com o Google Drive. Confira rede, DNS e proxy do backend.'
    elif isinstance(error, psycopg2.Error):
        reason = f'Falha no PostgreSQL local (SQLSTATE {error.pgcode or "indisponível"}).'
    elif isinstance(error, OSError):
        reason = f'Falha de acesso aos arquivos locais ({type(error).__name__}, errno={error.errno}). Confira espaço e permissões.'
    else:
        reason = f'Erro interno ({type(error).__name__}). Consulte o log do backend.'
    return f'Falha na {operation}. {reason} Etapa: {stage} Se houver restore-pending.json, preserve-o para revisão.'


def _run(identity, operation):
    def progress(message):
        with _lock:
            _jobs[identity].update(status='running', message=message)
        logging.getLogger(__name__).info('Operação %s: %s', identity, message)
    try:
        result = operation(progress)
    except Exception as error:
        # Não registrar mensagem/locals da exceção: podem conter SQL, dados
        # pessoais ou URLs autenticadas. Tipo e frames bastam para localizar a falha.
        frames = ' > '.join(f'{frame.name}:{frame.lineno}'
                            for frame in traceback.extract_tb(error.__traceback__))
        logging.getLogger(__name__).error('Operação %s falhou: %s; origem=%s', identity, type(error).__name__, frames)
        with _lock:
            job = _jobs[identity]
            detail = _failure_detail(error, job['kind'], job['message'])
            job.update(status='failed', message=detail, error_type=type(error).__name__)
    else:
        if _jobs[identity]['kind'] == 'sync':
            from .auto_sync import record_success
            try:
                record_success(_jobs[identity].get('_sync_generation'))
            except Exception as error:
                logging.getLogger(__name__).error('Sincronização concluída; atualização do estado automático falhou: %s', type(error).__name__)
        with _lock:
            _jobs[identity].update(status='completed', message=result['message'], result=result)


def start(kind, *, desktop=False, file_id=None, expected_sha256=None):
    with _lock:
        if any(job['status'] in ('queued', 'running') for job in _jobs.values()):
            raise HTTPException(409, 'Já existe um backup/restauração em andamento.')
        service._assert_ready()
        while len(_jobs) >= 50:
            _jobs.pop(next(iter(_jobs)))
        identity = str(uuid4())
        _jobs[identity] = dict(id=identity, kind=kind, status='queued', message='Aguardando início.')
        if kind == 'backup':
            operation = lambda progress: service.create_backup(desktop=desktop, progress=progress)
        elif kind == 'restore':
            operation = lambda progress: service.restore_backup(file_id, expected_sha256, desktop=desktop, progress=progress)
        elif kind == 'sync':
            from .synchronization import synchronize
            from .auto_sync import generation
            _jobs[identity]['_sync_generation'] = generation()
            operation = lambda progress: synchronize(desktop=desktop, progress=progress)
        else:
            _jobs.pop(identity)
            raise ValueError('Tipo de operação inválido.')
    _executor.submit(_run, identity, operation)
    return status(identity)


def status(identity):
    with _lock:
        if identity not in _jobs:
            raise HTTPException(404, 'Operação não encontrada. Se a API reiniciou, confira os dados e as cópias locais antes de repetir.')
        return {key: value for key, value in _jobs[identity].items() if not key.startswith('_')}
