from datetime import date
from typing import Any
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from backend.mac_api.core.wire import encode, decode
from . import analysis_archive
from .analysis_registration import register_analysis
from psycopg2 import Error as DatabaseError

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


@router.post('/thermography/analyses/register', status_code=201, tags=['Termografia'])
def register(payload: RegisteredAnalysisInput):
    try:
        return encode(register_analysis(**decode(payload.model_dump())))
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
def list_saved(athlete_id: int = Query(gt=0)):
    return encode(analysis_archive.list_analyses(athlete_id))


@router.get('/thermography/analyses/{athlete_id}/{collected_at}/{analysis_id}', tags=['Análises locais'])
def load(athlete_id: int, collected_at: date, analysis_id: UUID):
    try:
        return encode(analysis_archive.load_analysis(athlete_id, collected_at, analysis_id))
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail='Análise local não encontrada.') from error
