"""Filtros compartilhados pelas páginas de monitoramento."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import streamlit as st


PERIODS = {
    "Últimos 7 dias": 7,
    "Últimos 30 dias": 30,
    "Últimos 90 dias": 90,
    "Todo o histórico": None,
}


@dataclass
class FilteredRecords:
    selected_position: str | None
    selected_athletes: list[str]
    analysis_athletes: list[str]
    start_date: date
    end_date: date
    period_records: list[dict[str, object]]
    position_records: list[dict[str, object]]
    filtered_records: list[dict[str, object]]


def render_data_filters(records: list[dict[str, object]]) -> FilteredRecords:
    """Renderiza atleta, posição e período e retorna os recortes resultantes."""
    positions = sorted(
        {str(record["posicao"]) for record in records if record["posicao"]}
    )

    filters = st.columns(3)
    with filters[1]:
        selected_position = st.selectbox(
            "Posição",
            [None, *positions],
            format_func=lambda value: value or "Todas as posições",
        )

    available_athletes = sorted(
        {
            str(record["atleta"])
            for record in records
            if selected_position is None or record["posicao"] == selected_position
        }
    )
    with filters[0]:
        selected_athletes = st.multiselect(
            "Atletas",
            available_athletes,
            placeholder="Todos os atletas",
        )

    with filters[2]:
        selected_period = st.selectbox(
            "Período de referência",
            list(PERIODS),
            index=2,
        )

    analysis_athletes = selected_athletes or (
        available_athletes if selected_position else []
    )
    period_days = PERIODS[selected_period]
    if period_days is None:
        start_date = min(record["data_coleta"] for record in records)
        end_date = max(record["data_coleta"] for record in records)
    else:
        end_date = date.today()
        start_date = end_date - timedelta(days=period_days - 1)

    period_records = [
        record
        for record in records
        if start_date <= record["data_coleta"] <= end_date
    ]
    position_records = [
        record
        for record in period_records
        if selected_position is None or record["posicao"] == selected_position
    ]
    filtered_records = [
        record
        for record in position_records
        if not selected_athletes or record["atleta"] in selected_athletes
    ]

    return FilteredRecords(
        selected_position=selected_position,
        selected_athletes=selected_athletes,
        analysis_athletes=analysis_athletes,
        start_date=start_date,
        end_date=end_date,
        period_records=period_records,
        position_records=position_records,
        filtered_records=filtered_records,
    )
