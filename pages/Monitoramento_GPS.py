from __future__ import annotations

from statistics import pstdev

import plotly.graph_objects as go
from plotly.colors import qualitative
import streamlit as st

from chart_statistics import daily_statistics
from data_filters import alphabetical_key, render_data_filters
from gps_data import average, load_gps_records, numeric_value, opponents_by_date
from gps_import_ui import render_gps_import


st.set_page_config(
    page_title="MAC Performance | Monitoramento GPS",
    page_icon="📍",
    layout="wide",
)

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
) -> tuple[list[object], list[float], list[float]]:
    return daily_statistics(records, lambda record: metric_value(record, metric))


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
    color: str,
) -> None:
    dates, values, deviations = records_by_date(records, metric)
    if not dates:
        return
    unit = str(METRICS[metric]["unit"])
    daily_opponents = opponents_by_date(records)
    hover_data = [
        [deviation, daily_opponents.get(collection_date, "Não informado")]
        for collection_date, deviation in zip(dates, deviations)
    ]
    lower_limit = [value - deviation for value, deviation in zip(values, deviations)]
    upper_limit = [value + deviation for value, deviation in zip(values, deviations)]
    fill_color = color.replace("rgb(", "rgba(").replace(")", ", 0.18)")
    if color.startswith("#"):
        fill_color = (
            f"rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, "
            f"{int(color[5:7], 16)}, 0.18)"
        )
    figure.add_trace(
        go.Scatter(
            x=[*dates, *reversed(dates)],
            y=[*upper_limit, *reversed(lower_limit)],
            name=f"Faixa ± DP — {name}",
            legendgroup=name,
            mode="lines",
            line={"width": 0, "color": color},
            fill="toself",
            fillcolor=fill_color,
            hoverinfo="skip",
            showlegend=False,
        )
    )
    figure.add_trace(
        go.Scatter(
            x=dates,
            y=values,
            customdata=hover_data,
            name=name,
            legendgroup=name,
            mode="lines+markers" if highlight else "lines",
            line={"color": color},
            marker={"color": color},
            hovertemplate=(
                "%{x|%d/%m/%Y}<br>"
                f"Média: %{{y:.1f}} {unit}<br>"
                f"DP: %{{customdata[0]:.1f}} {unit}<br>"
                "Adversário: %{customdata[1]}"
                "<extra>%{fullData.name}</extra>"
            ),
        )
    )


st.title("Monitoramento GPS")
render_gps_import()

try:
    all_records = load_gps_records()
except Exception as error:
    st.error(f"Não foi possível carregar os dados de GPS: {error}")
    st.stop()

if not all_records:
    st.warning("A view de GPS não retornou registros.")
    st.stop()

filters = render_data_filters(all_records)
selected_position = filters.selected_position
analysis_athletes = filters.analysis_athletes
period_records = filters.period_records
filtered_records = filters.filtered_records

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
        with st.container(border=True):
            st.metric(
                f"Média de {metric.rsplit(' (', 1)[0]}",
                formatted_value(value, unit),
            )
            if deviation is not None:
                st.caption(f"± {deviation:.1f} {unit}")


def evolution_chart(metric: str) -> go.Figure:
    figure = go.Figure()
    series_index = 0
    for athlete in analysis_athletes:
        athlete_records = [
            record
            for record in filtered_records
            if record["atleta"] == athlete
        ]
        add_average_trace(
            figure,
            athlete_records,
            athlete,
            metric,
            highlight=True,
            color=qualitative.Plotly[series_index % len(qualitative.Plotly)],
        )
        series_index += 1

    reference_positions = (
        [selected_position]
        if selected_position
        else sorted(
            {
                str(record["posicao"])
                for record in all_records
                if record["atleta"] in analysis_athletes and record["posicao"]
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
            color=qualitative.Plotly[series_index % len(qualitative.Plotly)],
        )
        series_index += 1

    add_average_trace(
        figure,
        period_records,
        "Média do elenco",
        metric,
        highlight=not analysis_athletes,
        color=qualitative.Plotly[series_index % len(qualitative.Plotly)],
    )
    figure.update_layout(
        height=380,
        hovermode="x unified",
        xaxis_title="Data da coleta",
        yaxis_title=metric,
    )
    return figure


st.subheader("Evolução de carga e intensidade")
selected_variables = st.multiselect(
    "Variáveis",
    sorted(METRICS, key=alphabetical_key),
)

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
