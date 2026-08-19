"""Consultas e cálculos de leitura para os dados de salto."""

from __future__ import annotations

from statistics import fmean

import streamlit as st

from database import database_connection


@st.cache_data(ttl=300, show_spinner="Carregando dados de salto...")
def load_jump_records() -> list[dict[str, object]]:
    """Carrega a view de saltos usando exclusivamente a conexão read-only."""
    query = """
        SELECT
            atleta,
            posicao,
            grupo,
            data_coleta::date AS data_coleta,
            maior_cmj,
            maior_sj
        FROM public.vw_medidas_saltos
        ORDER BY data_coleta, atleta
    """
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            columns = [description.name for description in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def positive_number(value: object) -> float | None:
    """Converte números positivos e trata zero como ausência de medição."""
    if value is None:
        return None
    number = float(value)
    return number if number > 0 else None


def recorded_best(record: dict[str, object], test: str) -> float | None:
    """Retorna o maior salto registrado na coluna correspondente da view."""
    return positive_number(record.get(f"maior_{test}"))


def average(values: list[float | None]) -> float | None:
    valid_values = [value for value in values if value is not None]
    return fmean(valid_values) if valid_values else None
