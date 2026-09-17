"""Consultas e tratamento de leitura para os dados de GPS."""

from __future__ import annotations

from collections import defaultdict
import re
from statistics import fmean

import streamlit as st

from database import database_connection


@st.cache_data(ttl=300, show_spinner="Carregando dados de GPS...")
def load_gps_records() -> list[dict[str, object]]:
    """Carrega somente as métricas utilizadas pela página de GPS."""
    query = """
        SELECT
            atleta,
            posicao,
            grupo,
            data_coleta::date AS data_coleta,
            equipe,
            adversario,
            accel_de_cel_efforts,
            accel_de_cel_efforts_per_minute,
            distance_km,
            high_speed_distance,
            high_speed_efforts,
            max_acceleration,
            max_deceleration,
            maximum_velocity_km_h,
            meterage_per_minute,
            player_load_per_minute,
            sprint_efforts
        FROM public.vw_medidas_gps
        ORDER BY data_coleta, atleta
    """
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            columns = [description.name for description in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def numeric_value(record: dict[str, object], column: str) -> float | None:
    """Converte valores não negativos e preserva zero como medição válida."""
    value = record.get(column)
    if value is None:
        return None
    number = float(value)
    return number if number >= 0 else None


def average(values: list[float | None]) -> float | None:
    valid_values = [value for value in values if value is not None]
    return fmean(valid_values) if valid_values else None


def opponents_by_date(records: list[dict[str, object]]) -> dict[object, str]:
    """Agrupa os nomes únicos dos adversários por data de coleta."""
    grouped: dict[object, set[str]] = defaultdict(set)
    for record in records:
        opponent = str(record.get("adversario") or "").strip()
        team = str(record.get("equipe") or "").strip()
        displayed_opponent = opponent
        if opponent.casefold() == "mac" and team:
            displayed_opponent = team
        elif not opponent and team:
            match = re.fullmatch(r"(.+?)\s+[xX]\s+MAC", team, flags=re.IGNORECASE)
            displayed_opponent = match.group(1).strip() if match else ""
        if displayed_opponent:
            grouped[record["data_coleta"]].add(displayed_opponent)

    return {
        collection_date: " / ".join(sorted(opponents, key=str.casefold))
        for collection_date, opponents in grouped.items()
    }
