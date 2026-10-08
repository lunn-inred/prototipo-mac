from __future__ import annotations
import csv
import io
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo
from types import SimpleNamespace
from typing import Any, Mapping, Iterable

EXTRACTION_VERSION = 3
META = ['_arquivo']
class DuplicateThermographyError(ValueError): pass
class AthleteInUseError(ValueError): pass
def current_sao_paulo_date():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).date()
def athlete_display_name(athlete: Mapping[str, object]) -> str:
    athlete_id = int(athlete["id_atleta"])
    nickname = str(athlete.get("apelido") or "").strip()
    name = str(athlete.get("nome") or "").strip()
    return nickname or name or f"Jogador {athlete_id}"

def athlete_selection_label(athlete: Mapping[str, object]) -> str:
    return f"{athlete_display_name(athlete)} — ID {int(athlete['id_atleta'])}"

@dataclass
class LegacyThermographyRecord:
    athlete_id: int
    collected_at: date | datetime
    mass: float
    pain_score: int
    front: int
    back: int
    observations: str | None = None

@dataclass
class LegacyDocumentExtraction:
    pages: list[dict[str, object]]
    used_fallback: bool = False
    fallback_reason: str | None = None

def flatten(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {**{key: row[key] for key in META}, **row["dados"], **table.get("metadados", {})}
        for document in documents
        for table in document["tabelas"]
        for row in table["linhas"]
    ]

def csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    """Gera CSV compativel com Excel sem criar outro arquivo temporario."""
    fields = [field for field in META if any(field in row for row in rows)]
    seen = set(fields)
    for row in rows:
        for field in row:
            if field not in seen:
                fields.append(field)
                seen.add(field)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fields, delimiter=";", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return ("\ufeff" + output.getvalue()).encode("utf-8")

def payload_signature(payload: object) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
def _object(payload):
    if isinstance(payload, dict):
        values = {key: _object(value) for key, value in payload.items()}
        if isinstance(values.get('collected_at'), str):
            values['collected_at'] = datetime.fromisoformat(values['collected_at'])
        return SimpleNamespace(**values)
    if isinstance(payload, list): return [_object(item) for item in payload]
    return payload

def gps_preview_from_dict(payload): return _object(payload)
def gps_result_from_dict(payload): return _object(payload)
GpsImportPreview = SimpleNamespace
GpsImportResult = SimpleNamespace
def gps_view_preview_rows(document):
    return [vars(row) if isinstance(row, SimpleNamespace) else row for row in document.view_rows]

GPS_VIEW_COLUMNS = (
    "atleta",
    "posicao",
    "grupo",
    "data_coleta",
    "equipe",
    "adversario",
    "accel_de_cel_efforts",
    "accel_de_cel_efforts_per_minute",
    "distance_km",
    "high_speed_distance",
    "high_speed_efforts",
    "max_acceleration",
    "max_deceleration",
    "maximum_velocity_km_h",
    "meterage_per_minute",
    "player_load_per_minute",
    "sprint_efforts",
)

GPS_EDITOR_COLUMNS = (
    "nome_reconhecido",
    "jogador",
    "athlete_id",
    *(column for column in GPS_VIEW_COLUMNS if column != "atleta"),
)

def extracted_rows_to_gps_view(filename, rows, athletes=None):
    from frontend.streamlit.api_client.service_gateway import _request
    from frontend.streamlit.api_client.service_gateway import _json_value
    return _request('POST', '/api/v1/gps/editor-rows', json=_json_value({'filename': filename, 'rows': rows}))
def unique_matching_athlete_id(entered_name, athletes):
    from frontend.streamlit.api_client.service_gateway import _request
    return _request('POST', '/api/v1/athletes/match', json={'name': entered_name, 'athletes': athletes})['athlete_id']
