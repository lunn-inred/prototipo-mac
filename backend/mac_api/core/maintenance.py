"""Exclusão de manutenção para uma instância da API por banco/diretório."""
from contextlib import contextmanager
from threading import Condition
from fastapi import HTTPException

_condition = Condition()
_active = 0
_exclusive = False


def normal_operation():
    global _active
    from backend.mac_api.modules.backups.service import pending_recovery
    with _condition:
        if _exclusive:
            raise HTTPException(423, 'Backup/restauração em andamento. Aguarde antes de consultar ou alterar dados.')
        if pending_recovery():
            raise HTTPException(423, 'Há uma restauração interrompida. Revise restore-pending.json e a cópia preventiva antes de usar os dados.')
        _active += 1
    try:
        yield
    finally:
        with _condition:
            _active -= 1
            _condition.notify_all()


@contextmanager
def exclusive_operation():
    global _exclusive
    with _condition:
        if _exclusive:
            raise ValueError('Já existe uma operação de manutenção em andamento.')
        _exclusive = True
        if not _condition.wait_for(lambda: _active == 0, timeout=120):
            _exclusive = False
            raise ValueError('Há operações em andamento. Aguarde e tente novamente.')
    try:
        yield
    finally:
        with _condition:
            _exclusive = False
            _condition.notify_all()
