"""Consultas ao PostgreSQL usadas pela API.

As leituras de métricas continuam restritas às views públicas. O cadastro de
atletas é lido da tabela porque também possui CRUD próprio.
"""

from __future__ import annotations

from typing import Any

from database import database_connection


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
    measurements = _fetch_all(
        """
        SELECT mv.id_atleta, m.nome AS medida, mv.valor, mv.data::date AS data
        FROM public.medida_valor AS mv
        JOIN public.medida AS m ON m.id_medida = mv.id_medida
        WHERE LOWER(TRIM(m.nome)) IN (
            'maior_cmj', 'distance (km)', 'eva', 'eva dor', 'eva_dor'
        )
          AND mv.valor IS NOT NULL
        ORDER BY mv.data, mv.id_medida_valor
        """
    )
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
