"""Consultas e agregações somente leitura para o mural de jogadores."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from statistics import pstdev

import streamlit as st

from service_gateway import load_player_dashboard


METRIC_NAMES = {
    "maior_cmj": "cmj",
    "distance (km)": "distance",
    "eva": "eva",
    "eva dor": "eva",
    "eva_dor": "eva",
}


@st.cache_data(ttl=300, show_spinner="Carregando dados dos jogadores...")
def load_player_dashboard_data() -> tuple[
    list[dict[str, object]], list[dict[str, object]]
]:
    """Carrega cadastro e medidas usando exclusivamente a conexão read-only."""
    return load_player_dashboard()


def player_name(athlete: dict[str, object]) -> str:
    """Retorna o nome mais curto disponível para apresentação."""
    nickname = str(athlete.get("apelido") or "").strip()
    name = str(athlete.get("nome") or "").strip()
    return nickname or name or f"Jogador {athlete['id_atleta']}"


def group_measurements(
    measurements: list[dict[str, object]],
) -> dict[int, dict[str, list[tuple[date, float]]]]:
    """Organiza as medidas por jogador e por indicador do mural."""
    grouped: dict[int, dict[str, list[tuple[date, float]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for record in measurements:
        metric = METRIC_NAMES.get(str(record["medida"]).strip().casefold())
        if metric is None or record["data"] is None:
            continue
        grouped[int(record["id_atleta"])][metric].append(
            (record["data"], float(record["valor"]))
        )
    return grouped


def metric_summary(
    records: list[tuple[date, float]],
    start_date: date,
    end_date: date,
) -> tuple[float | None, float | None]:
    """Retorna a última medição e o DP populacional no período."""
    period_records = [
        (record_date, value)
        for record_date, value in records
        if start_date <= record_date <= end_date
    ]
    if not period_records:
        return None, None
    latest_value = max(period_records, key=lambda item: item[0])[1]
    values = [value for _, value in period_records]
    return latest_value, pstdev(values)


def latest_eva(records: list[tuple[date, float]]) -> float | None:
    """Retorna a EVA mais recente, independentemente do período visual."""
    if not records:
        return None
    return max(records, key=lambda item: item[0])[1]


def eva_classification(value: float | None) -> tuple[str, str]:
    """Classifica EVA: 0 sem dor, 1–3 leve, 4–7 moderada, 8–10 intensa."""
    if value is None:
        return "Sem EVA", "neutral"
    if value <= 0:
        return "Sem dor", "ok"
    if value <= 3:
        return "Leve", "ok"
    if value <= 7:
        return "Atenção", "attention"
    return "Risco", "risk"
