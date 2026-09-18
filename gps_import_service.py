from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from psycopg2.extras import execute_values

from database import database_write_connection


GPS_GROUP = "GPS"
IMPORT_LOCK_ID = 1_947_703_001
BASE_COLUMNS = {"_arquivo", "Nome", "Posição", "equipe", "adversario", "data_coleta"}
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
GPS_METRIC_VIEW_COLUMNS = {
    "Accel&Decel Efforts": "accel_de_cel_efforts",
    "Accel&Decel Efforts Per Minute": "accel_de_cel_efforts_per_minute",
    "Distance (km)": "distance_km",
    "High Speed Distance": "high_speed_distance",
    "High Speed Distance (km)": "high_speed_distance",
    "High Speed Efforts": "high_speed_efforts",
    "Max Acceleration": "max_acceleration",
    "Max Deceleration": "max_deceleration",
    "Maximum Velocity (km/h)": "maximum_velocity_km_h",
    "Meterage Per Minute": "meterage_per_minute",
    "Player Load Per Minute": "player_load_per_minute",
    "Sprint Efforts": "sprint_efforts",
}
GPS_VIEW_METRICS = {
    "accel_de_cel_efforts": "Accel&Decel Efforts",
    "accel_de_cel_efforts_per_minute": "Accel&Decel Efforts Per Minute",
    "distance_km": "Distance (km)",
    "high_speed_distance": "High Speed Distance",
    "high_speed_efforts": "High Speed Efforts",
    "max_acceleration": "Max Acceleration",
    "max_deceleration": "Max Deceleration",
    "maximum_velocity_km_h": "Maximum Velocity (km/h)",
    "meterage_per_minute": "Meterage Per Minute",
    "player_load_per_minute": "Player Load Per Minute",
    "sprint_efforts": "Sprint Efforts",
}
POSITION_NAMES = {
    "ca": "Centroavante",
    "centroavante": "Centroavante",
    "ext": "Extrema",
    "extrema": "Extrema",
    "gol": "Goleiro",
    "goleiro": "Goleiro",
    "ponta": "Ponta",
    "vol": "Volante",
    "volante": "Volante",
    "mei": "Meia",
    "meia": "Meia",
    "ld": "Lateral",
    "le": "Lateral",
    "lateral": "Lateral",
    "zag": "Zagueiro",
    "zagueiro": "Zagueiro",
    "ata": "Atacante",
    "atacante": "Atacante",
}


@dataclass(frozen=True)
class GpsFileMetadata:
    filename: str
    collected_at: datetime
    team: str
    opponent: str


@dataclass(frozen=True)
class GpsMeasurement:
    athlete: str
    position: str
    metric: str
    value: float
    text_value: str
    row_number: int


@dataclass(frozen=True)
class PreparedGpsDocument:
    metadata: GpsFileMetadata | None
    filename: str
    measurements: tuple[GpsMeasurement, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class GpsImportPreview:
    document: PreparedGpsDocument
    new_athletes: tuple[str, ...]
    new_match: bool
    new_metrics: tuple[str, ...]
    new_measurements: int
    duplicate_measurements: int
    warnings: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class GpsImportResult:
    filename: str
    inserted_measurements: int
    duplicate_measurements: int
    created_athletes: int
    created_match: bool
    created_metrics: int
    error: str | None = None


ConnectionFactory = Callable[[], AbstractContextManager[Any]]


def parse_metric_value(value: object) -> tuple[float, str]:
    if isinstance(value, bool):
        raise ValueError("valor booleano não é uma medição numérica")
    text = str(value).strip()
    if not text:
        raise ValueError("valor vazio")
    if "," in text and "." in text:
        raise ValueError("use apenas vírgula ou ponto como separador decimal")
    try:
        number = float(text.replace(",", "."))
    except (TypeError, ValueError) as error:
        raise ValueError(f"valor não numérico: {text}") from error
    if not math.isfinite(number):
        raise ValueError(f"valor não finito: {text}")
    return number, text


def clean_athlete_name(value: object) -> str:
    return str(value).split(",", 1)[0].strip()


def normalize_position(value: object) -> str:
    text = str(value).strip()
    normalized = unicodedata.normalize("NFKD", text.casefold())
    key = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    key = re.sub(r"[^a-z0-9]", "", key)
    if not key:
        raise ValueError("posição obrigatória")
    if key not in POSITION_NAMES:
        expected = ", ".join(sorted(set(POSITION_NAMES.values())))
        raise ValueError(f"posição desconhecida: {text}. Valores aceitos: {expected}")
    return POSITION_NAMES[key]


def normalize_position_if_known(value: object) -> str:
    """Normaliza a grade sem esconder um valor inválido que precisa de revisão."""
    try:
        return normalize_position(value)
    except ValueError:
        return str(value).strip()


def payload_signature(payload: object) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def gps_view_preview_rows(document: PreparedGpsDocument) -> list[dict[str, object]]:
    """Projeta as medições extraídas nas colunas da vw_medidas_gps."""
    if document.metadata is None:
        return []

    rows_by_athlete: dict[str, dict[str, object]] = {}
    for measurement in document.measurements:
        row = rows_by_athlete.setdefault(
            measurement.athlete,
            {
                **dict.fromkeys(GPS_VIEW_COLUMNS),
                "atleta": measurement.athlete,
                "posicao": measurement.position,
                "grupo": GPS_GROUP,
                "data_coleta": document.metadata.collected_at,
                "equipe": document.metadata.team,
                "adversario": document.metadata.opponent,
            },
        )
        view_column = GPS_METRIC_VIEW_COLUMNS.get(measurement.metric)
        if view_column:
            row[view_column] = measurement.value

    return list(rows_by_athlete.values())


def extracted_rows_to_gps_view(
    filename: str, rows: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Converte as linhas horizontais do OCR para o formato editável da view."""
    view_rows: list[dict[str, object]] = []
    for source in rows:
        row: dict[str, object] = {
            **dict.fromkeys(GPS_VIEW_COLUMNS),
            "atleta": clean_athlete_name(source.get("Nome", "")),
            "posicao": normalize_position_if_known(source.get("Posição", "")),
            "grupo": GPS_GROUP,
            "data_coleta": source.get("data_coleta"),
            "equipe": source.get("equipe"),
            "adversario": source.get("adversario"),
        }
        for metric, view_column in GPS_METRIC_VIEW_COLUMNS.items():
            raw_value = source.get(metric)
            if raw_value is None or str(raw_value).strip() == "":
                continue
            try:
                row[view_column] = parse_metric_value(raw_value)[0]
            except ValueError:
                # Preserva o OCR inválido para que o usuário possa corrigi-lo.
                row[view_column] = raw_value
        view_rows.append(row)
    return view_rows


def metadata_from_page_rows(filename: str, rows: list[dict[str, object]]) -> GpsFileMetadata:
    """Exige cabeçalhos válidos e consistentes nas páginas de um relatório."""
    metadata = None
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("linha inválida para leitura dos metadados da página")
        team = str(row.get("equipe") or "").strip()
        opponent = str(row.get("adversario") or "").strip()
        collected_at = row.get("data_coleta")
        if not team or not opponent or not isinstance(collected_at, datetime) or collected_at != collected_at:
            raise ValueError("equipe, adversário ou data ausentes no cabeçalho da página; extraia o PDF novamente")
        current = GpsFileMetadata(filename, collected_at, team, opponent)
        if metadata is not None and metadata != current:
            raise ValueError("as páginas do PDF possuem equipe, adversário ou data divergentes")
        metadata = current
    if metadata is None:
        raise ValueError("nenhum cabeçalho de página disponível")
    return metadata


def prepare_gps_documents(
    payload: list[dict[str, object]],
) -> list[PreparedGpsDocument]:
    prepared: list[PreparedGpsDocument] = []
    for item in payload:
        filename = Path(str(item.get("arquivo", ""))).name
        errors: list[str] = list(item.get("erros_extracao", []))
        rows = item.get("linhas", [])
        if not isinstance(rows, list) or not rows:
            errors.append(f"{filename}: nenhuma linha extraída para importar")
            rows = []

        try:
            metadata = metadata_from_page_rows(filename, rows)
        except (TypeError, ValueError) as error:
            metadata = None
            errors.append(f"{filename or 'arquivo sem nome'}: {error}")

        measurements: list[GpsMeasurement] = []
        seen_measurements: set[tuple[str, str]] = set()
        for row_number, row in enumerate(rows, 1):
            if not isinstance(row, dict):
                errors.append(f"{filename}, linha {row_number}: formato inválido")
                continue
            is_view_row = "atleta" in row or "posicao" in row
            athlete = clean_athlete_name(
                row.get("atleta", "") if is_view_row else row.get("Nome", "")
            )
            try:
                position = normalize_position(
                    row.get("posicao", "") if is_view_row else row.get("Posição", "")
                )
            except ValueError as error:
                position = ""
                errors.append(f"{filename}, linha {row_number}: {error}")
            if not athlete:
                errors.append(f"{filename}, linha {row_number}: atleta obrigatório")

            metric_count = 0
            metric_values = (
                (
                    metric_name,
                    row.get(view_column),
                )
                for view_column, metric_name in GPS_VIEW_METRICS.items()
            ) if is_view_row else row.items()
            for metric, raw_value in metric_values:
                metric_name = str(metric).strip()
                if metric_name in BASE_COLUMNS:
                    continue
                if raw_value is None or str(raw_value).strip() == "":
                    continue
                metric_count += 1
                try:
                    number, text_value = parse_metric_value(raw_value)
                except ValueError as error:
                    errors.append(
                        f"{filename}, linha {row_number}, {metric_name}: {error}"
                    )
                    continue
                key = (athlete, metric_name)
                if key in seen_measurements:
                    errors.append(
                        f"{filename}: medição repetida de {metric_name} para {athlete}"
                    )
                    continue
                seen_measurements.add(key)
                if athlete and position:
                    measurements.append(
                        GpsMeasurement(
                            athlete=athlete,
                            position=position,
                            metric=metric_name,
                            value=number,
                            text_value=text_value,
                            row_number=row_number,
                        )
                    )
            if metric_count == 0:
                errors.append(f"{filename}, linha {row_number}: nenhuma métrica preenchida")

        prepared.append(
            PreparedGpsDocument(
                metadata=metadata,
                filename=filename,
                measurements=tuple(measurements),
                errors=tuple(dict.fromkeys(errors)),
            )
        )
    return prepared


def _fetch_existing_athletes(
    cursor: Any, names: Iterable[str]
) -> dict[str, tuple[int, str | None]]:
    athlete_names = sorted(set(names))
    if not athlete_names:
        return {}
    cursor.execute(
        'SELECT id_atleta, apelido, posicao FROM public."atleta" WHERE apelido = ANY(%s)',
        (athlete_names,),
    )
    return {row[1]: (row[0], row[2]) for row in cursor.fetchall()}


def _fetch_match(cursor: Any, metadata: GpsFileMetadata) -> int | None:
    cursor.execute(
        '''
        SELECT id_partida FROM public."partida"
        WHERE equipe = %s AND adversario = %s AND data = %s
        ORDER BY id_partida LIMIT 1
        ''',
        (metadata.team, metadata.opponent, metadata.collected_at),
    )
    result = cursor.fetchone()
    return result[0] if result else None


def _fetch_group(cursor: Any) -> int | None:
    cursor.execute(
        'SELECT id_grupo_medida FROM public."grupo_medida" WHERE nome = %s '
        "ORDER BY id_grupo_medida LIMIT 1",
        (GPS_GROUP,),
    )
    result = cursor.fetchone()
    return result[0] if result else None


def _fetch_metrics(cursor: Any, group_id: int | None, names: Iterable[str]) -> dict[str, int]:
    metric_names = sorted(set(names))
    if group_id is None or not metric_names:
        return {}
    cursor.execute(
        '''
        SELECT id_medida, nome FROM public."medida"
        WHERE id_grupo_medida = %s AND nome = ANY(%s)
        ''',
        (group_id, metric_names),
    )
    return {row[1]: row[0] for row in cursor.fetchall()}


def _fetch_duplicate_pairs(
    cursor: Any,
    match_id: int | None,
    collected_at: datetime,
    athlete_ids: Iterable[int],
    metric_ids: Iterable[int],
) -> set[tuple[int, int]]:
    athletes = sorted(set(athlete_ids))
    metrics = sorted(set(metric_ids))
    if match_id is None or not athletes or not metrics:
        return set()
    cursor.execute(
        '''
        SELECT id_atleta, id_medida FROM public."medida_valor"
        WHERE id_partida = %s AND data = %s
          AND id_atleta = ANY(%s) AND id_medida = ANY(%s)
        ''',
        (match_id, collected_at, athletes, metrics),
    )
    return {(row[0], row[1]) for row in cursor.fetchall()}


def preview_gps_documents(
    documents: list[PreparedGpsDocument],
    connection_factory: ConnectionFactory = database_write_connection,
) -> list[GpsImportPreview]:
    previews: list[GpsImportPreview] = []
    for document in documents:
        if document.errors or document.metadata is None:
            previews.append(
                GpsImportPreview(document, (), False, (), 0, 0, (), document.errors)
            )
            continue
        try:
            with connection_factory() as connection, connection.cursor() as cursor:
                athletes = _fetch_existing_athletes(
                    cursor, (item.athlete for item in document.measurements)
                )
                match_id = _fetch_match(cursor, document.metadata)
                group_id = _fetch_group(cursor)
                metrics = _fetch_metrics(
                    cursor,
                    group_id,
                    (item.metric for item in document.measurements),
                )
                duplicate_pairs = _fetch_duplicate_pairs(
                    cursor,
                    match_id,
                    document.metadata.collected_at,
                    (value[0] for value in athletes.values()),
                    metrics.values(),
                )
                duplicates = sum(
                    1
                    for item in document.measurements
                    if item.athlete in athletes
                    and item.metric in metrics
                    and (athletes[item.athlete][0], metrics[item.metric])
                    in duplicate_pairs
                )
                extracted_positions = {
                    item.athlete: item.position for item in document.measurements
                }
                warnings = tuple(
                    f"{name}: posição existente '{position}' difere da extraída "
                    f"'{extracted_positions[name]}'"
                    for name, (_, position) in athletes.items()
                    if position and position != extracted_positions[name]
                )
                new_athletes = tuple(
                    sorted(
                        {item.athlete for item in document.measurements}
                        - set(athletes)
                    )
                )
                new_metrics = tuple(
                    sorted(
                        {item.metric for item in document.measurements} - set(metrics)
                    )
                )
                previews.append(
                    GpsImportPreview(
                        document=document,
                        new_athletes=new_athletes,
                        new_match=match_id is None,
                        new_metrics=new_metrics,
                        new_measurements=len(document.measurements) - duplicates,
                        duplicate_measurements=duplicates,
                        warnings=warnings,
                        errors=(),
                    )
                )
        except Exception as error:
            previews.append(
                GpsImportPreview(
                    document, (), False, (), 0, 0, (), (f"Falha ao validar no banco: {error}",)
                )
            )
    return previews


def _get_or_create_group(cursor: Any) -> tuple[int, bool]:
    group_id = _fetch_group(cursor)
    if group_id is not None:
        return group_id, False
    cursor.execute(
        'INSERT INTO public."grupo_medida" (nome) VALUES (%s) RETURNING id_grupo_medida',
        (GPS_GROUP,),
    )
    return cursor.fetchone()[0], True


def _get_or_create_athlete(cursor: Any, name: str, position: str) -> tuple[int, bool]:
    existing = _fetch_existing_athletes(cursor, [name])
    if name in existing:
        return existing[name][0], False
    cursor.execute(
        'INSERT INTO public."atleta" (apelido, posicao) VALUES (%s, %s) RETURNING id_atleta',
        (name, position),
    )
    return cursor.fetchone()[0], True


def _get_or_create_match(cursor: Any, metadata: GpsFileMetadata) -> tuple[int, bool]:
    match_id = _fetch_match(cursor, metadata)
    if match_id is not None:
        return match_id, False
    cursor.execute(
        '''
        INSERT INTO public."partida" (data, equipe, adversario)
        VALUES (%s, %s, %s) RETURNING id_partida
        ''',
        (metadata.collected_at, metadata.team, metadata.opponent),
    )
    return cursor.fetchone()[0], True


def _get_or_create_metric(cursor: Any, group_id: int, name: str) -> tuple[int, bool]:
    existing = _fetch_metrics(cursor, group_id, [name])
    if name in existing:
        return existing[name], False
    cursor.execute(
        '''
        INSERT INTO public."medida" (id_grupo_medida, nome)
        VALUES (%s, %s) RETURNING id_medida
        ''',
        (group_id, name),
    )
    return cursor.fetchone()[0], True


def import_gps_documents(
    documents: list[PreparedGpsDocument],
    connection_factory: ConnectionFactory = database_write_connection,
) -> list[GpsImportResult]:
    results: list[GpsImportResult] = []
    for document in documents:
        if document.errors or document.metadata is None:
            results.append(
                GpsImportResult(
                    document.filename,
                    0,
                    0,
                    0,
                    False,
                    0,
                    "; ".join(document.errors),
                )
            )
            continue
        try:
            with connection_factory() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (IMPORT_LOCK_ID,))
                group_id, _ = _get_or_create_group(cursor)
                match_id, created_match = _get_or_create_match(cursor, document.metadata)

                athlete_ids: dict[str, int] = {}
                created_athletes = 0
                positions = {item.athlete: item.position for item in document.measurements}
                for athlete, position in sorted(positions.items()):
                    athlete_id, created = _get_or_create_athlete(cursor, athlete, position)
                    athlete_ids[athlete] = athlete_id
                    created_athletes += int(created)

                metric_ids: dict[str, int] = {}
                created_metrics = 0
                for metric in sorted({item.metric for item in document.measurements}):
                    metric_id, created = _get_or_create_metric(cursor, group_id, metric)
                    metric_ids[metric] = metric_id
                    created_metrics += int(created)

                duplicate_pairs = _fetch_duplicate_pairs(
                    cursor,
                    match_id,
                    document.metadata.collected_at,
                    athlete_ids.values(),
                    metric_ids.values(),
                )
                values = []
                duplicates = 0
                for item in document.measurements:
                    pair = (athlete_ids[item.athlete], metric_ids[item.metric])
                    if pair in duplicate_pairs:
                        duplicates += 1
                        continue
                    duplicate_pairs.add(pair)
                    values.append(
                        (
                            pair[0],
                            match_id,
                            pair[1],
                            item.value,
                            item.text_value,
                            document.metadata.collected_at,
                        )
                    )
                if values:
                    execute_values(
                        cursor,
                        '''
                        INSERT INTO public."medida_valor"
                            (id_atleta, id_partida, id_medida, valor, valor_texto, data)
                        VALUES %s
                        ''',
                        values,
                    )
                results.append(
                    GpsImportResult(
                        filename=document.filename,
                        inserted_measurements=len(values),
                        duplicate_measurements=duplicates,
                        created_athletes=created_athletes,
                        created_match=created_match,
                        created_metrics=created_metrics,
                    )
                )
        except Exception as error:
            results.append(GpsImportResult(document.filename, 0, 0, 0, False, 0, str(error)))
    return results
