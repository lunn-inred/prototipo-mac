from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import pstdev

import plotly.graph_objects as go
import streamlit as st

from gps_data import average, load_gps_records, numeric_value


st.set_page_config(
    page_title="MAC Performance | Monitoramento GPS",
    page_icon="📍",
    layout="wide",
)

PERIODS = {
    "Últimos 7 dias": 7,
    "Últimos 30 dias": 30,
    "Últimos 90 dias": 90,
    "Todo o histórico": None,
}

METRICS = {
    "Esforços de aceleração/desaceleração (n)": {
        "column": "accel_de_cel_efforts",
        "unit": "eventos",
        "factor": 1.0,
    },
    "Esforços de aceleração/desaceleração por minuto": {
        "column": "accel_de_cel_efforts_per_minute",
        "unit": "eventos/min",
        "factor": 1.0,
    },
    "Distância total (km)": {
        "column": "distance_km",
        "unit": "km",
        "factor": 1.0,
    },
    "Distância em alta velocidade — HSR (m)": {
        "column": "high_speed_distance",
        "unit": "m",
        "factor": 1000.0,
    },
    "Esforços em alta velocidade (n)": {
        "column": "high_speed_efforts",
        "unit": "eventos",
        "factor": 1.0,
    },
    "Aceleração máxima": {
        "column": "max_acceleration",
        "unit": "m/s²",
        "factor": 1.0,
    },
    "Desaceleração máxima": {
        "column": "max_deceleration",
        "unit": "m/s²",
        "factor": 1.0,
    },
    "Velocidade máxima": {
        "column": "maximum_velocity_km_h",
        "unit": "km/h",
        "factor": 1.0,
    },
    "Metragem por minuto": {
        "column": "meterage_per_minute",
        "unit": "m/min",
        "factor": 1.0,
    },
    "Player load por minuto": {
        "column": "player_load_per_minute",
        "unit": "u.a./min",
        "factor": 1.0,
    },
    "Número de sprints (n)": {
        "column": "sprint_efforts",
        "unit": "n",
        "factor": 1.0,
    },
}


def metric_value(record: dict[str, object], metric: str) -> float | None:
    definition = METRICS[metric]
    value = numeric_value(record, str(definition["column"]))
    return None if value is None else value * float(definition["factor"])


def records_by_date(
    records: list[dict[str, object]], metric: str
) -> tuple[list[object], list[float]]:
    grouped: dict[object, list[float]] = defaultdict(list)
    for record in records:
        value = metric_value(record, metric)
        if value is not None:
            grouped[record["data_coleta"]].append(value)

    dates = sorted(grouped)
    return dates, [average(grouped[collection_date]) for collection_date in dates]


def average_and_standard_deviation(
    records: list[dict[str, object]], metric: str
) -> tuple[float | None, float | None]:
    values = [
        value
        for record in records
        if (value := metric_value(record, metric)) is not None
    ]
    if not values:
        return None, None
    return average(values), pstdev(values)


def formatted_value(value: float | None, unit: str) -> str:
    if value is None:
        return "Sem dados"
    return f"{value:.1f} {unit}"


def add_average_trace(
    figure: go.Figure,
    records: list[dict[str, object]],
    name: str,
    metric: str,
    *,
    highlight: bool = False,
) -> None:
    dates, values = records_by_date(records, metric)
    if not dates:
        return
    figure.add_trace(
        go.Scatter(
            x=dates,
            y=values,
            name=name,
            mode="lines+markers" if highlight else "lines",
        )
    )


def add_athlete_deviation(
    figure: go.Figure,
    records: list[dict[str, object]],
    athlete: str,
    metric: str,
) -> None:
    dates, values = records_by_date(records, metric)
    if not dates:
        return

    standard_deviation = pstdev(values)
    lower_limit = [value - standard_deviation for value in values]
    upper_limit = [value + standard_deviation for value in values]
    figure.add_trace(
        go.Scatter(
            x=[*dates, *reversed(dates)],
            y=[*upper_limit, *reversed(lower_limit)],
            name=f"Faixa ± DP — {athlete}",
            mode="lines",
            line={"width": 0},
            fill="toself",
            opacity=0.18,
            hoverinfo="skip",
            zorder=-1,
        )
    )


st.title("Monitoramento GPS")

try:
    all_records = load_gps_records()
except Exception as error:
    st.error(f"Não foi possível carregar os dados de GPS: {error}")
    st.stop()

if not all_records:
    st.warning("A view de GPS não retornou registros.")
    st.stop()

positions = sorted(
    {str(record["posicao"]) for record in all_records if record["posicao"]}
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
        for record in all_records
        if selected_position is None or record["posicao"] == selected_position
    }
)
with filters[0]:
    selected_athlete = st.selectbox(
        "Atleta",
        [None, *available_athletes],
        format_func=lambda value: value or "Todos os atletas",
    )
with filters[2]:
    selected_period = st.selectbox(
        "Período de referência",
        list(PERIODS),
        index=2,
    )

period_days = PERIODS[selected_period]
if period_days is None:
    start_date = min(record["data_coleta"] for record in all_records)
    end_date = max(record["data_coleta"] for record in all_records)
else:
    end_date = date.today()
    start_date = end_date - timedelta(days=period_days - 1)

period_records = [
    record
    for record in all_records
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
    if selected_athlete is None or record["atleta"] == selected_athlete
]

st.caption(
    "Fonte: public.vw_medidas_gps · HSR convertido de quilômetros para metros."
)

if not filtered_records:
    st.warning("Não há medições de GPS para os filtros selecionados.")
    st.stop()

card_metrics = [
    "Distância total (km)",
    "Distância em alta velocidade — HSR (m)",
]
for column, metric in zip(st.columns(len(card_metrics)), card_metrics):
    value, deviation = average_and_standard_deviation(filtered_records, metric)
    unit = str(METRICS[metric]["unit"])
    with column:
        st.metric(f"Média de {metric.rsplit(' (', 1)[0]}", formatted_value(value, unit))
        if deviation is not None:
            st.caption(f"± {deviation:.1f} {unit}")


def evolution_chart(metric: str) -> go.Figure:
    figure = go.Figure()
    if selected_athlete is not None:
        athlete_records = [
            record
            for record in filtered_records
            if record["atleta"] == selected_athlete
        ]
        add_average_trace(
            figure,
            athlete_records,
            selected_athlete,
            metric,
            highlight=True,
        )

        reference_positions = (
            [selected_position]
            if selected_position
            else sorted(
                {
                    str(record["posicao"])
                    for record in all_records
                    if record["atleta"] == selected_athlete and record["posicao"]
                }
            )
        )
        for reference_position in reference_positions:
            add_average_trace(
                figure,
                [
                    record
                    for record in period_records
                    if record["posicao"] == reference_position
                ],
                f"Média {reference_position}",
                metric,
            )
        add_athlete_deviation(
            figure,
            athlete_records,
            selected_athlete,
            metric,
        )
    elif selected_position is not None:
        add_average_trace(
            figure,
            position_records,
            f"Média {selected_position}",
            metric,
            highlight=True,
        )

    add_average_trace(
        figure,
        period_records,
        "Média do elenco",
        metric,
        highlight=selected_athlete is None and selected_position is None,
    )
    figure.update_layout(
        height=380,
        hovermode="x unified",
        xaxis_title="Data da coleta",
        yaxis_title=metric,
    )
    return figure


st.subheader("Evolução de carga e intensidade")
selected_variables = st.multiselect("Variáveis", list(METRICS))

if not selected_variables:
    st.info("Selecione ao menos uma variável.")
else:
    for variable in selected_variables:
        st.markdown(f"#### {variable}")
        chart = evolution_chart(variable)
        if not chart.data:
            st.info(f"Não há dados de {variable} para os filtros selecionados.")
        else:
            st.plotly_chart(chart, width="stretch", key=f"gps_{variable}")
