from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from backend.mac_api.core.settings import api_key
from backend.mac_api.modules.google_auth import enabled
from . import jobs, service


def require_google_configuration():
    if not enabled() or not api_key():
        raise HTTPException(403, 'Backups exigem login Google e chave de API configurados.')


router = APIRouter(prefix='/backups', tags=['Backups'], dependencies=[Depends(require_google_configuration)])


class BackupInput(BaseModel):
    desktop: bool = False


class RestoreInput(BackupInput):
    file_id: str = Field(min_length=1, max_length=255, pattern=r'^[A-Za-z0-9_-]+$')
    expected_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    confirm: bool = False


@router.get('')
def list_backups(desktop: bool = False):
    return service.list_backups(desktop=desktop)


@router.post('', status_code=202)
def create_backup(payload: BackupInput):
    return jobs.start('backup', desktop=payload.desktop)


@router.post('/restore', status_code=202)
def restore_backup(payload: RestoreInput):
    if not payload.confirm:
        raise HTTPException(422, 'Confirme explicitamente a substituição do banco local antes de restaurar.')
    return jobs.start('restore', desktop=payload.desktop, file_id=payload.file_id, expected_sha256=payload.expected_sha256)


@router.get('/jobs/{identity}')
def status(identity: str):
    return jobs.status(identity)
