"""Consultas ao PostgreSQL usadas pela API.

As leituras de métricas continuam restritas às views públicas. O cadastro de
atletas é lido da tabela porque também possui CRUD próprio.
"""

from __future__ import annotations

from typing import Any

from backend.mac_api.core.database import database_connection


def _fetch_all(query: str, parameters: tuple[object, ...] = ()) -> list[dict[str, Any]]:
    with database_connection() as connection, connection.cursor() as cursor:
        cursor.execute(query, parameters)
        columns = [description.name for description in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def list_athletes() -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT id_atleta, nome, apelido, nome_alternativo, posicao, grupo,
               data_nascimento
        FROM public.atleta
        ORDER BY COALESCE(NULLIF(TRIM(apelido), ''), NULLIF(TRIM(nome), '')),
                 id_atleta
        """
    )


def get_athlete(athlete_id: int) -> dict[str, Any] | None:
    records = _fetch_all(
        """
        SELECT id_atleta, nome, apelido, nome_alternativo, posicao, grupo,
               data_nascimento
        FROM public.atleta
        WHERE id_atleta = %s
        """,
        (int(athlete_id),),
    )
    return records[0] if records else None


def player_dashboard_data() -> dict[str, list[dict[str, Any]]]:
    athletes = list_athletes()
    from backend.mac_api.modules.athletes.athlete_matching import unique_matching_athlete_id
    measurements = []
    sources = (
        (jump_records(), 'maior_cmj', 'maior_cmj', 'atleta'),
        (gps_records(), 'distance_km', 'distance (km)', 'atleta'),
        (thermography_history(), 'eva_dor', 'eva_dor', 'jogador'),
    )
    for records, column, metric, name_column in sources:
        for record in records:
            athlete_id = record.get('id_atleta')
            if athlete_id is None:
                athlete_id = unique_matching_athlete_id(record.get(name_column), athletes)
            if athlete_id is None or record.get(column) is None:
                continue
            collected_at = record['data_coleta']
            if hasattr(collected_at, 'hour'):
                collected_at = collected_at.date()
            measurements.append({'id_atleta': athlete_id, 'medida': metric,
                                 'valor': record[column], 'data': collected_at})
    measurements.sort(key=lambda item: item['data'])
    return {"athletes": athletes, "measurements": measurements}


def jump_records() -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT atleta, posicao, grupo, data_coleta::date AS data_coleta,
               maior_cmj, maior_sj
        FROM public.vw_medidas_saltos
        ORDER BY data_coleta, atleta
        """
    )


def jump_collections() -> list[dict[str, Any]]:
    """Lista coletas editáveis com os IDs necessários ao CRUD."""
    records = _fetch_all(
        """
        SELECT v.atleta, v.posicao, v.grupo, v.data_coleta::date AS data_coleta,
               v.cmj1, v.cmj2, v.cmj3, v.maior_cmj,
               v.sj1, v.sj2, v.sj3, v.maior_sj
        FROM public.vw_medidas_saltos v
        ORDER BY v.data_coleta::date DESC, v.atleta
        """,
    )
    from backend.mac_api.modules.athletes.athlete_matching import unique_matching_athlete_id
    athletes = list_athletes()
    by_id = {athlete['id_atleta']: athlete for athlete in athletes}
    collections = []
    for record in records:
        athlete_id = unique_matching_athlete_id(record['atleta'], athletes)
        # Nunca permitir edição/exclusão por uma associação ambígua.
        if athlete_id is None:
            continue
        athlete = by_id[athlete_id]
        collections.append({**record, 'id_atleta': athlete_id,
                            'atleta': athlete['nome'], 'apelido': athlete.get('apelido')})
    return collections


def gps_records() -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT atleta, posicao, grupo, data_coleta::date AS data_coleta,
               equipe, adversario, accel_de_cel_efforts,
               accel_de_cel_efforts_per_minute, distance_km,
               high_speed_distance, high_speed_efforts, max_acceleration,
               max_deceleration, maximum_velocity_km_h, meterage_per_minute,
               player_load_per_minute, sprint_efforts
        FROM public.vw_medidas_gps
        ORDER BY data_coleta, atleta
        """
    )


def thermography_history(athlete_id: int | None = None) -> list[dict[str, Any]]:
    parameter = int(athlete_id) if athlete_id is not None else None
    return _fetch_all(
        """
        SELECT id_atleta, jogador, data_coleta, massa, eva_dor, frente,
               verso, observacoes
        FROM public.vw_medida_termografia
        WHERE (%s IS NULL OR id_atleta = %s)
        ORDER BY data_coleta DESC, jogador
        """,
        (parameter, parameter),
    )
