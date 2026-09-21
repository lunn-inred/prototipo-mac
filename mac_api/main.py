"""FastAPI que expõe os casos de uso do MAC Performance."""

from __future__ import annotations

import base64
import io
import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

import data_repository
from api_serialization import gps_preview_to_dict, gps_result_to_dict
from athlete_service import AthleteInUseError, create_athlete, delete_athlete, update_athlete
from gps_extraction import extract_uploaded_pdfs
from gps_import_service import import_gps_documents, prepare_gps_documents, preview_gps_documents
from legacy_thermography import extract_document, validate_athlete_rows
from settings import api_key, cors_origins, setting
from thermography_analysis_service import (
    analyze_thermography_view, extract_thermography_scale,
)
from thermography_service import (
    DuplicateThermographyError,
    LegacyThermographyRecord,
    save_image_thermography,
    save_legacy_thermography,
)
from .schemas import (
    AthleteCreated, AthleteInput, GpsPayload, LegacyImport, LegacyValidation,
    ThermographyInput,
)


def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    expected = api_key()
    if expected and (not x_api_key or not secrets.compare_digest(x_api_key, expected)):
        raise HTTPException(status_code=401, detail="Chave da API inválida ou ausente.")


router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])


@router.get("/athletes", tags=["Atletas"])
def athletes() -> list[dict[str, Any]]:
    return data_repository.list_athletes()


@router.get("/athletes/{athlete_id}", tags=["Atletas"])
def athlete(athlete_id: int) -> dict[str, Any]:
    record = data_repository.get_athlete(athlete_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Atleta não encontrado.")
    return record


@router.post("/athletes", response_model=AthleteCreated, status_code=201, tags=["Atletas"])
def athlete_create(payload: AthleteInput) -> dict[str, int]:
    athlete_id = create_athlete(**payload.model_dump())
    return {"id_atleta": athlete_id}


@router.put("/athletes/{athlete_id}", status_code=204, tags=["Atletas"])
def athlete_update(athlete_id: int, payload: AthleteInput) -> None:
    update_athlete(athlete_id, **payload.model_dump())


@router.delete("/athletes/{athlete_id}", status_code=204, tags=["Atletas"])
def athlete_delete(athlete_id: int) -> None:
    delete_athlete(athlete_id)


@router.get("/players/dashboard", tags=["Painel"])
def dashboard() -> dict[str, Any]:
    return data_repository.player_dashboard_data()


@router.get("/jumps", tags=["Medições"])
def jumps() -> list[dict[str, Any]]:
    return data_repository.jump_records()


@router.get("/gps", tags=["GPS"])
def gps() -> list[dict[str, Any]]:
    return data_repository.gps_records()


@router.post("/gps/extract", tags=["GPS"])
async def gps_extract(files: Annotated[list[UploadFile], File()]) -> list[dict[str, Any]]:
    inputs = [(item.filename or "relatorio.pdf", await item.read()) for item in files]
    return await run_in_threadpool(extract_uploaded_pdfs, inputs)


@router.post("/gps/preview", tags=["GPS"])
def gps_preview(payload: GpsPayload) -> list[dict[str, Any]]:
    prepared = prepare_gps_documents(payload.documents)
    return [gps_preview_to_dict(item) for item in preview_gps_documents(prepared)]


@router.post("/gps/import", tags=["GPS"])
def gps_import(payload: GpsPayload) -> list[dict[str, Any]]:
    prepared = prepare_gps_documents(payload.documents)
    return [gps_result_to_dict(item) for item in import_gps_documents(prepared)]


@router.get("/thermography", tags=["Termografia"])
def thermography_history(athlete_id: int | None = Query(default=None)) -> list[dict[str, Any]]:
    return data_repository.thermography_history(athlete_id)


@router.post("/thermography/scale", tags=["Termografia"])
async def thermography_scale(
    file: Annotated[UploadFile, File()],
) -> dict[str, float]:
    return await run_in_threadpool(
        extract_thermography_scale, await file.read()
    )


@router.post("/thermography/analyze", tags=["Termografia"])
async def thermography_analyze(
    file: Annotated[UploadFile, File()],
    view: Annotated[str, Form()],
    minimum_temperature: Annotated[float, Form()],
    maximum_temperature: Annotated[float, Form()],
    threshold: Annotated[float, Form()],
) -> dict[str, Any]:
    content = await file.read()
    return await run_in_threadpool(
        analyze_thermography_view, content, view=view,
        minimum_temperature=minimum_temperature,
        maximum_temperature=maximum_temperature, threshold=threshold,
    )


@router.post("/thermography", status_code=201, tags=["Termografia"])
def thermography_create(payload: ThermographyInput) -> dict[str, int]:
    count = save_image_thermography(**payload.model_dump())
    return {"inserted_measurements": count}


def _page_to_json(page: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in page.items() if key != "diagnostic"}
    image = page.get("diagnostic")
    if image is not None:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        result["diagnostic_png"] = base64.b64encode(buffer.getvalue()).decode("ascii")
    return result


@router.post("/thermography/legacy/extract", tags=["Termografia"])
async def legacy_extract(files: Annotated[list[UploadFile], File()]) -> list[dict[str, Any]]:
    result = []
    llama_key = setting("LLAMA_CLOUD_API_KEY")
    for item in files:
        content = await item.read()
        extraction = await run_in_threadpool(
            extract_document, content, item.filename or "documento",
            api_key=llama_key,
        )
        result.append({
            "filename": item.filename,
            "used_fallback": extraction.used_fallback,
            "fallback_reason": extraction.fallback_reason,
            "pages": [_page_to_json(page) for page in extraction.pages],
        })
    return result


@router.post("/thermography/legacy/validate-athletes", tags=["Termografia"])
def legacy_validate(payload: LegacyValidation) -> list[dict[str, Any]]:
    return validate_athlete_rows(payload.rows, data_repository.list_athletes())


@router.post("/thermography/legacy/import", status_code=201, tags=["Termografia"])
def legacy_import(payload: LegacyImport) -> dict[str, int]:
    records = [LegacyThermographyRecord(**item.model_dump()) for item in payload.records]
    return {"inserted_measurements": save_legacy_thermography(records)}


def create_app() -> FastAPI:
    app = FastAPI(
        title="MAC Performance API",
        version="1.0.0",
        description="API dos cadastros, medições e análises do protótipo MAC Performance.",
    )
    origins = cors_origins()
    if origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=origins, allow_credentials=True,
            allow_methods=["*"], allow_headers=["*"],
        )

    @app.exception_handler(AthleteInUseError)
    async def athlete_in_use_handler(_request: Any, error: AthleteInUseError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(DuplicateThermographyError)
    async def duplicate_handler(_request: Any, error: DuplicateThermographyError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(ValueError)
    async def validation_handler(_request: Any, error: ValueError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.get("/health", tags=["Infraestrutura"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)
    return app


app = create_app()
