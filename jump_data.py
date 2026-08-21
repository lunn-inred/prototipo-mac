"""Consultas e cálculos de leitura para os dados de salto."""

from __future__ import annotations

from collections import defaultdict
from statistics import fmean, pstdev

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


def metric_summary(
    records: list[dict[str, object]], test: str
) -> tuple[float | None, float | None]:
    """Retorna média e desvio padrão populacional dos saltos válidos."""
    values = [
        value
        for record in records
        if (value := recorded_best(record, test)) is not None
    ]
    if not values:
        return None, None
    return fmean(values), pstdev(values)


def _latest_position(records: list[dict[str, object]]) -> str:
    """Obtém a posição não vazia do registro mais recente do atleta."""
    positioned_records = [record for record in records if record.get("posicao")]
    if not positioned_records:
        return "Sem posição"
    latest_record = max(
        positioned_records,
        key=lambda record: record.get("data_coleta") or "",
    )
    return str(latest_record["posicao"])


def _athlete_summaries(
    records: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Agrega as medições por atleta, dando peso igual a cada jogador."""
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        grouped[str(record["atleta"])].append(record)

    summaries: list[dict[str, object]] = []
    for athlete, athlete_records in grouped.items():
        cmj_mean, cmj_deviation = metric_summary(athlete_records, "cmj")
        sj_mean, sj_deviation = metric_summary(athlete_records, "sj")
        summaries.append(
            {
                "athlete": athlete,
                "position": _latest_position(athlete_records),
                "cmj_mean": cmj_mean,
                "cmj_deviation": cmj_deviation,
                "sj_mean": sj_mean,
                "sj_deviation": sj_deviation,
            }
        )
    return summaries


def _position_metric_reference(
    summaries: list[dict[str, object]], position: str, metric_key: str
) -> tuple[float, float] | None:
    """Calcula média e DP entre as médias individuais de uma posição."""
    values = [
        float(summary[metric_key])
        for summary in summaries
        if summary["position"] == position and summary[metric_key] is not None
    ]
    if len(values) < 2:
        return None
    deviation = pstdev(values)
    if deviation == 0:
        return None
    return fmean(values), deviation


def _analysis_label(score: float | None) -> tuple[int, str]:
    if score is None:
        return 3, "Dados insuficientes"
    formatted_score = f"{score:+.2f}".replace(".", ",")
    if score >= 0.5:
        return 0, f"Acima da média ({formatted_score} DP)"
    if score <= -0.5:
        return 2, f"Abaixo da média ({formatted_score} DP)"
    return 1, f"Na média ({formatted_score} DP)"


def build_jump_comparison(
    display_records: list[dict[str, object]],
    reference_records: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Monta o comparativo dos atletas contra jogadores da mesma posição.

    A referência usa a distribuição das médias individuais, e não todos os
    registros brutos, para que cada atleta tenha o mesmo peso estatístico.
    """
    display_summaries = _athlete_summaries(display_records)
    reference_summaries = _athlete_summaries(reference_records)
    rows: list[dict[str, object]] = []

    for summary in display_summaries:
        position = str(summary["position"])
        z_scores: list[float] = []
        for metric_key in ("cmj_mean", "sj_mean"):
            athlete_mean = summary[metric_key]
            reference = _position_metric_reference(
                reference_summaries, position, metric_key
            )
            if athlete_mean is not None and reference is not None:
                position_mean, position_deviation = reference
                z_scores.append(
                    (float(athlete_mean) - position_mean) / position_deviation
                )

        score = fmean(z_scores) if z_scores else None
        rank, analysis = _analysis_label(score)
        rows.append(
            {
                **summary,
                "analysis": analysis,
                "analysis_score": score,
                "analysis_rank": rank,
            }
        )

    return sorted(
        rows,
        key=lambda row: (
            int(row["analysis_rank"]),
            -(float(row["analysis_score"]) if row["analysis_score"] is not None else 0),
            str(row["athlete"]),
        ),
    )
