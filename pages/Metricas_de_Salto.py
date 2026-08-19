from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
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


def latest_value_and_standard_deviation(
    records: list[dict[str, object]], metric: str
) -> tuple[float | None, float | None]:
    _, values = records_by_date(records, metric)
    if not values:
        return None, None
    return values[-1], pstdev(values)


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

    standard_deviation = pstdev(values) if highlight else None
    error_bar = (
        {
            "type": "constant",
            "value": standard_deviation,
            "visible": True,
        }
        if standard_deviation is not None
        else None
    )

    if chart_type == "Gráfico de linha":
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=values,
                name=name,
                mode="lines+markers" if highlight else "lines",
            )
        )
    elif chart_type == "Gráfico de barras":
        figure.add_trace(
            go.Bar(
                x=dates,
                y=values,
                name=name,
                error_y=error_bar,
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
    if not dates or chart_type == "Gráfico de barras":
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

available_athlete_ids = sorted(
    {
        str(record["atleta"])
        for record in all_records
        if selected_position is None or record["posicao"] == selected_position
    },
    key=athlete_names.get,
)

with filters[0]:
    selected_athlete = st.selectbox(
        "Atleta",
        [None, *available_athlete_ids],
        format_func=lambda athlete_id: (
            "Todos os atletas"
            if athlete_id is None
            else athlete_names[athlete_id]
        ),
    )
with filters[2]:
    selected_period = st.selectbox("Período de referência", list(PERIODS), index=2)

latest_date = max(record["data_coleta"] for record in all_records)
period_days = PERIODS[selected_period]
cutoff_date = latest_date - timedelta(days=period_days - 1) if period_days else None
period_records = [
    record
    for record in all_records
    if cutoff_date is None or record["data_coleta"] >= cutoff_date
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
    f"Fonte: public.vw_medidas_saltos · períodos calculados a partir da coleta mais recente ({latest_date:%d/%m/%Y})."
)

if not filtered_records:
    st.warning("Não há coletas para os filtros selecionados.")
    st.stop()

cmj_value, cmj_standard_deviation = latest_value_and_standard_deviation(
    filtered_records, "cmj"
)
sj_value, sj_standard_deviation = latest_value_and_standard_deviation(
    filtered_records, "sj"
)
valid_collections = sum(
    recorded_best(record, "cmj") is not None
    or recorded_best(record, "sj") is not None
    for record in filtered_records
)

metrics = st.columns(3)
cmj_metric_label = (
    "Média do CMJ na última coleta"
    if selected_athlete is None
    else "CMJ na última coleta"
)
sj_metric_label = (
    "Média do SJ na última coleta"
    if selected_athlete is None
    else "SJ na última coleta"
)
with metrics[0]:
    st.metric(cmj_metric_label, metric_text(cmj_value))
    if cmj_standard_deviation is not None:
        st.caption(standard_deviation_text(cmj_standard_deviation))
with metrics[1]:
    st.metric(sj_metric_label, metric_text(sj_value))
    if sj_standard_deviation is not None:
        st.caption(standard_deviation_text(sj_standard_deviation))
metrics[2].metric("Coletas com medição", valid_collections)


def evolution_chart(metric: str, chart_type: str) -> go.Figure:
    figure = go.Figure()
    if selected_athlete is not None:
        add_evolution_trace(
            figure,
            filtered_records,
            athlete_names[selected_athlete],
            metric=metric,
            chart_type=chart_type,
            highlight=True,
        )

    reference_position = selected_position
    if selected_athlete is not None and reference_position is None:
        reference_position = next(
            (
                str(record["posicao"])
                for record in all_records
                if record["atleta"] == selected_athlete and record["posicao"]
            ),
            None,
        )
    if reference_position:
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
    if selected_athlete is not None:
        add_athlete_deviation(
            figure,
            filtered_records,
            athlete_names[selected_athlete],
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


def radar_chart(metric: str) -> go.Figure | None:
    athlete_records = [
        record
        for record in all_records
        if record["atleta"] == selected_athlete
    ]
    athlete_dates, _ = records_by_date(athlete_records, metric)
    radar_dates = athlete_dates[-5:]
    if not radar_dates:
        return None

    reference_position = selected_position or next(
        (
            str(record["posicao"])
            for record in athlete_records
            if record["posicao"]
        ),
        None,
    )
    scopes = [(athlete_names[selected_athlete], athlete_records)]
    if reference_position:
        scopes.append(
            (
                f"Média {reference_position}",
                [
                    record
                    for record in all_records
                    if record["posicao"] == reference_position
                ],
            )
        )
    scopes.append(("Média do elenco", all_records))

    date_labels = [date.strftime("%d/%m/%Y") for date in radar_dates]
    figure = go.Figure()
    for scope_name, scope_records in scopes:
        dates, values = records_by_date(scope_records, metric)
        values_by_date = dict(zip(dates, values))
        radar_values = [values_by_date.get(date) for date in radar_dates]
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


if selected_athlete is not None:
    charts = st.columns(2)
    with charts[0]:
        radar_metric = st.selectbox("Métrica do radar", ["CMJ", "SJ"])
        st.subheader("Radar temporal de saltos")
        radar_figure = radar_chart(radar_metric.lower())
        if radar_figure is None:
            st.info(f"O atleta não possui coletas válidas de {radar_metric}.")
        else:
            st.plotly_chart(radar_figure, width="stretch")
    with charts[1]:
        evolution_controls = st.columns(2)
        with evolution_controls[0]:
            evolution_metric = st.selectbox("Métrica", ["CMJ", "SJ"])
        with evolution_controls[1]:
            evolution_chart_type = st.selectbox(
                "Tipo de gráfico",
                ["Gráfico de linha", "Gráfico de barras", "Box plot"],
            )
        st.subheader(f"Evolução do {evolution_metric}")
        st.plotly_chart(
            evolution_chart(evolution_metric.lower(), evolution_chart_type),
            width="stretch",
        )
