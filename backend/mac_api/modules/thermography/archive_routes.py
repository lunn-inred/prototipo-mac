from datetime import date
from typing import Any
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from backend.mac_api.core.wire import encode, decode
from . import analysis_archive
from .analysis_registration import register_analysis, replace_analysis, AnalysisConflictError, AnalysisChangedError
from .thermography_service import DuplicateThermographyError
from psycopg2 import Error as DatabaseError
from . import drafts
import logging

router = APIRouter()


class LocalAnalysisInput(BaseModel):
    athlete_id: int = Field(gt=0)
    athlete_name: str = Field(min_length=1, max_length=250)
    collected_at: date
    mass: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    pain_score: int | None = Field(default=None, ge=0, le=10)
    observations: str = Field(default='', max_length=10000)
    views: dict[str, Any]


class RegisteredAnalysisInput(LocalAnalysisInput):
    mass: float = Field(gt=0, allow_inf_nan=False)
    pain_score: int = Field(ge=0, le=10)
    overwrite: bool = False
    draft_id: UUID | None = None
    draft_revision: str | None = None


class UpdatedAnalysisInput(RegisteredAnalysisInput):
    expected_revision: str = Field(min_length=1)


def _complete(payload, operation, source=None):
    parameters = decode(payload.model_dump())
    identity = parameters.pop('draft_id')
    revision = parameters.pop('draft_revision')
    with drafts.LOCK:
        if identity:
            try:
                state = drafts.check(str(identity), revision)
            except FileNotFoundError as error:
                raise AnalysisChangedError('O rascunho não está mais disponível. Abra a lista novamente.') from error
            original = state.get('source')
            if original:
                if not source or str(source['analysis_id']) != str(original['id']) or source['athlete_id'] != int(original['athlete_id']) or source['collected_at'].isoformat() != str(original['collected_at']) or parameters.get('expected_revision') != original['created_at']:
                    raise ValueError('Finalize o rascunho pela edição de sua análise original.')
            elif source:
                raise ValueError('Este rascunho ainda não possui análise completa original.')
            else:
                parameters['analysis_id'] = str(identity)
            partial, _ = drafts._read(str(identity))
            if partial.get('sql_pair'):
                parameters.update(partial_pair=partial['sql_pair'], partial_revision=partial['sql_revision'])
        conflicts = [entry for entry in drafts.list_saved(parameters['athlete_id'])
                     if entry['collected_at'] == parameters['collected_at'] and entry['id'] != str(identity)]
        if conflicts and not parameters.get('overwrite'):
            raise AnalysisConflictError('Uma análise do atleta já foi realizada nessa data. Deseja sobrescrevê-la?')
        result = operation(**parameters)
        for pending_id in ({str(identity)} if identity else set()) | {entry['id'] for entry in conflicts}:
            try:
                drafts.discard(pending_id)
            except OSError:
                logging.getLogger(__name__).warning('Análise registrada; limpeza do rascunho requer revisão.')
                result['draft_cleanup_pending'] = True
        return encode(result)


@router.put('/thermography/analyses/{athlete_id}/{collected_at}/{analysis_id}', tags=['Termografia'])
def update(athlete_id: int, collected_at: date, analysis_id: UUID, payload: UpdatedAnalysisInput):
    try:
        source = dict(athlete_id=athlete_id, collected_at=collected_at, analysis_id=analysis_id)
        return _complete(payload, lambda **values: replace_analysis(source=source, **values), source)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail='Análise original não encontrada. Abra a lista novamente.') from error
    except AnalysisConflictError as error:
        raise HTTPException(status_code=409, detail={'code': 'analysis_date_conflict', 'message': str(error)}) from error
    except AnalysisChangedError as error:
        raise HTTPException(status_code=409, detail={'code': 'analysis_changed', 'message': str(error)}) from error
    except (KeyError, TypeError) as error:
        raise ValueError('Dados da análise inválidos.') from error
    except (OSError, DatabaseError, RuntimeError) as error:
        raise HTTPException(status_code=503, detail='Não foi possível salvar as alterações. Confira banco e arquivos antes de reenviar.') from error


@router.post('/thermography/analyses/register', status_code=201, tags=['Termografia'])
def register(payload: RegisteredAnalysisInput):
    try:
        return _complete(payload, register_analysis)
    except AnalysisChangedError as error:
        raise HTTPException(status_code=409, detail={'code': 'analysis_changed', 'message': str(error)}) from error
    except (AnalysisConflictError, DuplicateThermographyError) as error:
        raise HTTPException(status_code=409, detail={'code': 'analysis_date_conflict',
            'message': 'Uma análise do atleta já foi realizada nessa data. Deseja sobrescrevê-la?'}) from error
    except (KeyError, TypeError) as error:
        raise ValueError('Dados da análise inválidos.') from error
    except (OSError, DatabaseError, RuntimeError) as error:
        raise HTTPException(status_code=503, detail='Não foi possível concluir o registro da análise. Confira o banco local e as permissões de MAC_ANALYSES_DIR antes de tentar novamente.') from error


@router.post('/thermography/analyses', status_code=201, tags=['Análises locais'])
def save(payload: LocalAnalysisInput):
    try:
        return encode(analysis_archive.save_analysis(**decode(payload.model_dump())))
    except (KeyError, TypeError) as error:
        raise ValueError('Dados da análise local inválidos.') from error
    except OSError as error:
        raise HTTPException(status_code=503, detail='Não foi possível gravar os arquivos. Confira MAC_ANALYSES_DIR e as permissões da pasta no servidor.') from error


@router.get('/thermography/analyses', tags=['Análises locais'])
def list_saved(athlete_id: int = Query(ge=0), include_drafts: bool = False):
    entries = analysis_archive.list_analyses(athlete_id) if athlete_id else []
    all_partial = drafts.list_saved()
    edited_ids = {entry['source']['id'] for entry in all_partial if entry.get('sql_pair') and entry.get('source')}
    partial_pairs = {(entry['sql_pair'][0], entry['sql_pair'][1]) for entry in all_partial if entry.get('sql_pair')}
    entries = [entry for entry in entries if entry['id'] not in edited_ids and
               (entry['athlete_id'], entry['collected_at'].isoformat()) not in partial_pairs]
    if include_drafts:
        partial = [entry for entry in all_partial if entry['athlete_id'] == athlete_id]
        pending_ids = {entry['id'] for entry in partial}
        entries = [entry for entry in entries if entry['id'] not in pending_ids] + partial
    return encode(entries)


class DraftInput(BaseModel):
    state: dict[str, Any]
    draft_id: UUID | None = None
    expected_revision: str | None = None
    overwrite: bool = False


@router.post('/thermography/drafts', tags=['Termografia'])
def save_draft(payload: DraftInput):
    try:
        return encode(drafts.save(decode(payload.state), identity=payload.draft_id,
            expected_revision=payload.expected_revision, overwrite=payload.overwrite))
    except AnalysisConflictError as error:
        raise HTTPException(409, detail={'code': 'analysis_date_conflict', 'message': str(error)}) from error
    except AnalysisChangedError as error:
        raise HTTPException(409, detail={'code': 'analysis_changed', 'message': str(error)}) from error
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('Dados do rascunho inválidos.') from error
    except (OSError, DatabaseError) as error:
        raise HTTPException(503, detail='Não foi possível salvar o rascunho. Confira os arquivos locais e o banco.') from error


@router.get('/thermography/drafts/{identity}', tags=['Termografia'])
def load_draft(identity: UUID):
    try:
        return encode(drafts.load(str(identity)))
    except FileNotFoundError as error:
        raise HTTPException(404, detail='Rascunho não encontrado.') from error


@router.get('/thermography/analyses/{athlete_id}/{collected_at}/{analysis_id}', tags=['Análises locais'])
def load(athlete_id: int, collected_at: date, analysis_id: UUID):
    try:
        return encode(analysis_archive.load_analysis(athlete_id, collected_at, analysis_id))
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail='Análise local não encontrada.') from error
