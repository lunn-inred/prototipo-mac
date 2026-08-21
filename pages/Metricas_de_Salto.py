from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import pstdev

import plotly.graph_objects as go
import streamlit as st

from jump_data import average, load_jump_records, recorded_best


st.set_page_config(
    page_title="MAC Performance | Métricas de Salto",
    page_icon="🔷",
    layout="wide",
)

PERIODS = {
    "Últimos 7 dias": 7,
    "Últimos 30 dias": 30,
    "Últimos 90 dias": 90,
    "Todo o histórico": None,
}


def records_by_date(
    records: list[dict[str, object]], metric: str
) -> tuple[list[object], list[float]]:
    grouped: dict[object, list[float]] = defaultdict(list)
    for record in records:
        value = recorded_best(record, metric)
        if value is not None:
            grouped[record["data_coleta"]].append(value)

    dates = sorted(grouped)
    values = [average(grouped[date]) for date in dates]
    return dates, [value for value in values if value is not None]


def average_and_standard_deviation(
    records: list[dict[str, object]], metric: str
) -> tuple[float | None, float | None]:
    values = [
        value
        for record in records
        if (value := recorded_best(record, metric)) is not None
    ]
    if not values:
        return None, None
    return average(values), pstdev(values)


def metric_text(value: float | None) -> str:
    return f"{value:.1f} cm" if value is not None else "Sem dados"


def standard_deviation_text(value: float | None) -> str | None:
    return f"± {value:.1f} cm" if value is not None else None


def add_evolution_trace(
    figure: go.Figure,
    records: list[dict[str, object]],
    name: str,
    *,
    metric: str,
    chart_type: str,
    highlight: bool = False,
) -> None:
    dates, values = records_by_date(records, metric)
    if not dates:
        return

    if chart_type == "Gráfico de linha":
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=values,
                name=name,
                mode="lines+markers" if highlight else "lines",
            )
        )
    else:
        figure.add_trace(
            go.Box(
                y=values,
                name=name,
                boxmean=True,
                boxpoints="all",
                jitter=0.2,
                pointpos=0,
            )
        )


def add_athlete_deviation(
    figure: go.Figure,
    records: list[dict[str, object]],
    name: str,
    metric: str,
    chart_type: str,
) -> None:
    dates, values = records_by_date(records, metric)
    if not dates:
        return

    standard_deviation = pstdev(values)
    if chart_type == "Gráfico de linha":
        lower_limit = [value - standard_deviation for value in values]
        upper_limit = [value + standard_deviation for value in values]
        figure.add_trace(
            go.Scatter(
                x=[*dates, *reversed(dates)],
                y=[*upper_limit, *reversed(lower_limit)],
                name=f"Faixa ± DP — {name}",
                mode="lines",
                line={"width": 0},
                fill="toself",
                opacity=0.18,
                hoverinfo="skip",
                zorder=-1,
            )
        )
    else:
        figure.add_trace(
            go.Scatter(
                x=[name],
                y=[average(values)],
                name=f"Média ± DP — {name}",
                mode="markers",
                marker={"symbol": "diamond", "size": 10},
                error_y={
                    "type": "constant",
                    "value": standard_deviation,
                    "visible": True,
                },
            )
        )


st.title("Métricas de Salto")

try:
    all_records = load_jump_records()
except Exception as error:
    st.error(f"Não foi possível carregar os dados de salto: {error}")
    st.stop()

if not all_records:
    st.warning("A view de saltos não retornou registros.")
    st.stop()

athlete_names = {
    str(record["atleta"]): str(record["atleta"])
    for record in all_records
}
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
    },
    key=athlete_names.get,
)

with filters[0]:
    selected_athletes = st.multiselect(
        "Atletas",
        available_athletes,
        placeholder="Todos os atletas",
    )
analysis_athletes = selected_athletes or (
    available_athletes if selected_position else []
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
    if not selected_athletes or record["atleta"] in selected_athletes
]


if not filtered_records:
    st.warning("Não há coletas para os filtros selecionados.")
    st.stop()

cmj_value, cmj_standard_deviation = average_and_standard_deviation(
    filtered_records, "cmj"
)
sj_value, sj_standard_deviation = average_and_standard_deviation(
    filtered_records, "sj"
)
valid_collections = sum(
    recorded_best(record, "cmj") is not None
    or recorded_best(record, "sj") is not None
    for record in filtered_records
)

metrics = st.columns(3)
with metrics[0]:
    st.metric("Média do CMJ", metric_text(cmj_value))
    if cmj_standard_deviation is not None:
        st.caption(standard_deviation_text(cmj_standard_deviation))
with metrics[1]:
    st.metric("Média do SJ", metric_text(sj_value))
    if sj_standard_deviation is not None:
        st.caption(standard_deviation_text(sj_standard_deviation))
metrics[2].metric("Coletas com medição", valid_collections)


def evolution_chart(metric: str, chart_type: str) -> go.Figure:
    figure = go.Figure()
    athlete_record_groups: list[tuple[str, list[dict[str, object]]]] = []
    for athlete in analysis_athletes:
        athlete_records = [
            record
            for record in filtered_records
            if record["atleta"] == athlete
        ]
        athlete_record_groups.append((athlete, athlete_records))
        add_evolution_trace(
            figure,
            athlete_records,
            athlete_names[athlete],
            metric=metric,
            chart_type=chart_type,
            highlight=True,
        )

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
        add_evolution_trace(
            figure,
            [
                record
                for record in period_records
                if record["posicao"] == reference_position
            ],
            f"Média {reference_position}",
            metric=metric,
            chart_type=chart_type,
        )

    add_evolution_trace(
        figure,
        period_records,
        "Média do elenco",
        metric=metric,
        chart_type=chart_type,
    )
    for athlete, athlete_records in athlete_record_groups:
        add_athlete_deviation(
            figure,
            athlete_records,
            athlete_names[athlete],
            metric,
            chart_type,
        )
    figure.update_layout(
        height=420,
        hovermode="x unified" if chart_type != "Box plot" else "closest",
        yaxis_title=f"{metric.upper()} (cm)",
        xaxis_title=(
            "Distribuição por série"
            if chart_type == "Box plot"
            else "Data da coleta"
        ),
        barmode="group",
    )
    return figure


def configure_radar_layout(figure: go.Figure, metric: str) -> go.Figure:
    figure.update_layout(
        height=520,
        paper_bgcolor="rgba(0, 0, 0, 0)",
        plot_bgcolor="rgba(0, 0, 0, 0)",
        font={"color": "#FAFAFA"},
        polar={
            "bgcolor": "rgba(0, 0, 0, 0)",
            "radialaxis": {
                "visible": True,
                "title": {"text": f"{metric.upper()} (cm)"},
                "gridcolor": "rgba(250, 250, 250, 0.20)",
                "linecolor": "rgba(250, 250, 250, 0.35)",
                "tickfont": {"color": "#FAFAFA"},
            },
            "angularaxis": {
                "gridcolor": "rgba(250, 250, 250, 0.20)",
                "linecolor": "rgba(250, 250, 250, 0.35)",
                "tickfont": {"color": "#FAFAFA"},
            },
        },
    )
    return figure


def temporal_radar_chart(metric: str) -> go.Figure | None:
    history_records = [
        record
        for record in all_records
        if record["data_coleta"] <= end_date
        and record["atleta"] in analysis_athletes
    ]
    available_dates, _ = records_by_date(history_records, metric)
    radar_dates = available_dates[-5:]
    if not radar_dates:
        return None

    scopes: list[tuple[str, list[dict[str, object]]]] = []
    for athlete in analysis_athletes:
        scopes.append(
            (
                athlete_names[athlete],
                [
                    record
                    for record in history_records
                    if record["atleta"] == athlete
                ],
            )
        )

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
        scopes.append(
            (
                f"Média {reference_position}",
                [
                    record
                    for record in all_records
                    if record["data_coleta"] <= end_date
                    and record["posicao"] == reference_position
                ],
            )
        )
    scopes.append(
        (
            "Média do elenco",
            [
                record
                for record in all_records
                if record["data_coleta"] <= end_date
            ],
        )
    )

    date_labels = [radar_date.strftime("%d/%m/%Y") for radar_date in radar_dates]
    figure = go.Figure()
    for scope_name, scope_records in scopes:
        dates, values = records_by_date(scope_records, metric)
        values_by_date = dict(zip(dates, values))
        radar_values = [values_by_date.get(radar_date) for radar_date in radar_dates]
        if not any(value is not None for value in radar_values):
            continue
        figure.add_trace(
            go.Scatterpolar(
                r=[*radar_values, radar_values[0]],
                theta=[*date_labels, date_labels[0]],
                name=scope_name,
                mode="lines+markers",
                fill="toself",
                opacity=0.65,
            )
        )

    return configure_radar_layout(figure, metric)


def athlete_radar_chart(metric: str) -> go.Figure | None:
    athlete_labels: list[str] = []
    radar_values: list[float] = []
    for athlete in analysis_athletes:
        athlete_average = average(
            [
                recorded_best(record, metric)
                for record in filtered_records
                if record["atleta"] == athlete
            ]
        )
        if athlete_average is not None:
            athlete_labels.append(athlete_names[athlete])
            radar_values.append(athlete_average)

    if len(radar_values) < 3:
        return None

    figure = go.Figure(
        go.Scatterpolar(
            r=[*radar_values, radar_values[0]],
            theta=[*athlete_labels, athlete_labels[0]],
            name=f"Média do {metric.upper()}",
            mode="lines+markers",
            fill="toself",
            opacity=0.65,
        )
    )

    return configure_radar_layout(figure, metric)


if analysis_athletes:
    selected_metric = st.selectbox("Métrica dos gráficos", ["CMJ", "SJ"])

    st.subheader(f"Evolução do {selected_metric}")
    st.plotly_chart(
        evolution_chart(selected_metric.lower(), "Gráfico de linha"),
        width="stretch",
    )

    st.subheader(f"Distribuição do {selected_metric}")
    st.plotly_chart(
        evolution_chart(selected_metric.lower(), "Box plot"),
        width="stretch",
    )

    radars = st.columns(2)
    with radars[0]:
        st.subheader(f"Últimas cinco datas de {selected_metric}")
        temporal_radar = temporal_radar_chart(selected_metric.lower())
        if temporal_radar is None:
            st.info(f"Não há dados válidos de {selected_metric} até {end_date:%d/%m/%Y}.")
        else:
            st.plotly_chart(temporal_radar, width="stretch")

    if len(analysis_athletes) >= 3:
        with radars[1]:
            st.subheader(f"Comparativo de {selected_metric} por atleta")
            athlete_radar = athlete_radar_chart(selected_metric.lower())
            if athlete_radar is None:
                st.info(
                    f"São necessários pelo menos três atletas com dados válidos "
                    f"de {selected_metric} no período."
                )
            else:
                st.plotly_chart(athlete_radar, width="stretch")
