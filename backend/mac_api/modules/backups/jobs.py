"""Uma tarefa por vez; polling não depende do timeout de uma requisição longa."""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from uuid import uuid4
from fastapi import HTTPException
from . import service

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='mac-backup')
_lock = Lock()
_jobs = {}


def _run(identity, operation):
    def progress(message):
        with _lock:
            _jobs[identity].update(status='running', message=message)
    try:
        result = operation(progress)
    except Exception as error:
        detail = error.detail if isinstance(error, HTTPException) else str(error) if isinstance(error, ValueError) else 'Falha no backup/restauração. Confira a conexão, o espaço local e as permissões. Se houver restore-pending.json, preserve-o e revise a cópia preventiva antes de reenviar.'
        with _lock:
            _jobs[identity].update(status='failed', message=detail)
    else:
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
        else:
            _jobs.pop(identity)
            raise ValueError('Tipo de operação inválido.')
    _executor.submit(_run, identity, operation)
    return status(identity)


def status(identity):
    with _lock:
        if identity not in _jobs:
            raise HTTPException(404, 'Operação não encontrada. Se a API reiniciou, confira os dados e as cópias locais antes de repetir.')
        return dict(_jobs[identity])
