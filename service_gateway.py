"""Ponte usada pelo Streamlit: API remota ou serviços locais compatíveis."""

from __future__ import annotations

import base64
import io
from datetime import date, datetime
from typing import Any

import httpx
from PIL import Image

import data_repository
from api_serialization import gps_preview_from_dict, gps_result_from_dict
from athlete_service import create_athlete as local_create_athlete
from athlete_service import delete_athlete as local_delete_athlete
from athlete_service import update_athlete as local_update_athlete
from gps_extraction import extract_uploaded_pdfs as local_extract_uploaded_pdfs
from gps_import_service import import_gps_documents, prepare_gps_documents, preview_gps_documents
from legacy_thermography import LegacyDocumentExtraction, extract_document, validate_athlete_rows
from settings import api_base_url, api_key, setting
from thermography_analysis_service import (
    analyze_thermography_view as local_analyze,
    extract_thermography_scale as local_extract_scale,
)
from thermography_service import LegacyThermographyRecord, save_image_thermography as local_save_image
from thermography_service import save_legacy_thermography as local_save_legacy


class ApiClientError(ValueError):
    pass


def remote_api_enabled() -> bool:
    return api_base_url() is not None


def _request(method: str, path: str, **kwargs: Any) -> Any:
    headers = dict(kwargs.pop("headers", {}))
    if api_key():
        headers["X-API-Key"] = str(api_key())
    timeout = float(setting("MAC_API_TIMEOUT_SECONDS", "300") or 300)
    try:
        response = httpx.request(
            method, f"{api_base_url()}{path}", headers=headers,
            timeout=timeout, **kwargs,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        try:
            detail = error.response.json().get("detail")
        except Exception:
            detail = None
        raise ApiClientError(detail or "A API recusou a operação.") from error
    except httpx.HTTPError as error:
        raise ApiClientError("Não foi possível comunicar com a API.") from error
    return None if response.status_code == 204 else response.json()


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _parse_date_fields(records: list[dict[str, Any]], *fields: str) -> list[dict[str, Any]]:
    for record in records:
        for field in fields:
            value = record.get(field)
            if isinstance(value, str):
                try:
                    record[field] = datetime.fromisoformat(value).date()
                except ValueError:
                    pass
    return records


def load_player_dashboard() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = _request("GET", "/api/v1/players/dashboard") if remote_api_enabled() else data_repository.player_dashboard_data()
    return _parse_date_fields(data["athletes"], "data_nascimento"), _parse_date_fields(data["measurements"], "data")


def load_athletes() -> list[dict[str, Any]]:
    records = _request("GET", "/api/v1/athletes") if remote_api_enabled() else data_repository.list_athletes()
    return _parse_date_fields(records, "data_nascimento")


def load_jump_records() -> list[dict[str, Any]]:
    records = _request("GET", "/api/v1/jumps") if remote_api_enabled() else data_repository.jump_records()
    return _parse_date_fields(records, "data_coleta")


def load_gps_records() -> list[dict[str, Any]]:
    records = _request("GET", "/api/v1/gps") if remote_api_enabled() else data_repository.gps_records()
    return _parse_date_fields(records, "data_coleta")


def load_thermography_history(athlete_id: int | None = None) -> list[dict[str, Any]]:
    if remote_api_enabled():
        params = {} if athlete_id is None else {"athlete_id": athlete_id}
        return _parse_date_fields(_request("GET", "/api/v1/thermography", params=params), "data_coleta")
    return data_repository.thermography_history(athlete_id)


def create_athlete(**values: Any) -> int:
    if not remote_api_enabled():
        return local_create_athlete(**values)
    return int(_request("POST", "/api/v1/athletes", json=_json_value(values))["id_atleta"])


def update_athlete(athlete_id: int, **values: Any) -> None:
    if not remote_api_enabled():
        local_update_athlete(athlete_id, **values)
        return
    _request("PUT", f"/api/v1/athletes/{athlete_id}", json=_json_value(values))


def delete_athlete(athlete_id: int) -> None:
    if not remote_api_enabled():
        local_delete_athlete(athlete_id)
        return
    _request("DELETE", f"/api/v1/athletes/{athlete_id}")


def extract_uploaded_pdfs(files: list[tuple[str, bytes]]) -> list[dict[str, Any]]:
    if not remote_api_enabled():
        return local_extract_uploaded_pdfs(files)
    multipart = [("files", (name, content, "application/pdf")) for name, content in files]
    return _request("POST", "/api/v1/gps/extract", files=multipart)


def preview_gps_payload(payload: list[dict[str, Any]]) -> list[Any]:
    if not remote_api_enabled():
        return preview_gps_documents(prepare_gps_documents(payload))
    return [gps_preview_from_dict(item) for item in _request("POST", "/api/v1/gps/preview", json={"documents": payload})]


def import_gps_payload(payload: list[dict[str, Any]]) -> list[Any]:
    if not remote_api_enabled():
        return import_gps_documents(prepare_gps_documents(payload))
    return [gps_result_from_dict(item) for item in _request("POST", "/api/v1/gps/import", json={"documents": payload})]


def extract_thermography_scale(content: bytes) -> dict[str, float]:
    if not remote_api_enabled():
        return local_extract_scale(content)
    return _request(
        "POST", "/api/v1/thermography/scale",
        files={"file": ("termografia.jpg", content, "image/jpeg")},
    )


def analyze_thermography_view(content: bytes, *, view: str, minimum_temperature: float, maximum_temperature: float, threshold: float) -> dict[str, Any]:
    if not remote_api_enabled():
        return local_analyze(content, view=view, minimum_temperature=minimum_temperature, maximum_temperature=maximum_temperature, threshold=threshold)
    return _request(
        "POST", "/api/v1/thermography/analyze",
        files={"file": ("termografia.jpg", content, "image/jpeg")},
        data={"view": view, "minimum_temperature": minimum_temperature, "maximum_temperature": maximum_temperature, "threshold": threshold},
    )


def save_image_thermography(**values: Any) -> int:
    if not remote_api_enabled():
        return local_save_image(**values)
    return int(_request("POST", "/api/v1/thermography", json=_json_value(values))["inserted_measurements"])


def extract_legacy_documents(files: list[tuple[str, bytes]]) -> list[tuple[str, LegacyDocumentExtraction]]:
    if not remote_api_enabled():
        key = setting("LLAMA_CLOUD_API_KEY")
        return [(name, extract_document(content, name, api_key=key)) for name, content in files]
    multipart = [("files", (name, content, "application/octet-stream")) for name, content in files]
    response = _request("POST", "/api/v1/thermography/legacy/extract", files=multipart)
    results = []
    for document in response:
        pages = []
        for raw_page in document["pages"]:
            page = dict(raw_page)
            encoded = page.pop("diagnostic_png", None)
            page["diagnostic"] = Image.open(io.BytesIO(base64.b64decode(encoded))).copy() if encoded else None
            pages.append(page)
        results.append((document["filename"], LegacyDocumentExtraction(pages, document["used_fallback"], document.get("fallback_reason"))))
    return results


def validate_legacy_athletes(rows: list[dict[str, Any]], athletes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not remote_api_enabled():
        return validate_athlete_rows(rows, athletes)
    return _request("POST", "/api/v1/thermography/legacy/validate-athletes", json={"rows": rows})


def save_legacy_thermography(records: list[LegacyThermographyRecord]) -> int:
    if not remote_api_enabled():
        return local_save_legacy(records)
    payload = {"records": [
        {
            "athlete_id": item.athlete_id,
            "collected_at": item.collected_at.isoformat(),
            "mass": item.mass,
            "pain_score": item.pain_score,
            "front": item.front,
            "back": item.back,
            "observations": item.observations,
        } for item in records
    ]}
    return int(_request("POST", "/api/v1/thermography/legacy/import", json=payload)["inserted_measurements"])
