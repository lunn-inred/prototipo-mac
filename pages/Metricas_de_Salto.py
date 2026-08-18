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


def add_average_trace(
    figure: go.Figure,
    records: list[dict[str, object]],
    name: str,
    *,
    mode: str = "lines",
) -> None:
    dates, values = records_by_date(records, "cmj")
    if dates:
        figure.add_trace(go.Scatter(x=dates, y=values, name=name, mode=mode))


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
    int(record["id_atleta"]): str(record["atleta"])
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
        int(record["id_atleta"])
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
    if selected_athlete is None or record["id_atleta"] == selected_athlete
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
metrics[0].metric(
    "CMJ na última coleta",
    metric_text(cmj_value),
    standard_deviation_text(cmj_standard_deviation),
    delta_color="off",
)
metrics[1].metric(
    "SJ na última coleta",
    metric_text(sj_value),
    standard_deviation_text(sj_standard_deviation),
    delta_color="off",
)
metrics[2].metric("Coletas com medição", valid_collections)


def comparison_chart() -> go.Figure:
    figure = go.Figure()
    selection_label = (
        athlete_names[selected_athlete]
        if selected_athlete is not None
        else selected_position or "Todos os atletas"
    )
    scopes = [(selection_label, filtered_records)]

    reference_position = selected_position
    if selected_athlete is not None and reference_position is None:
        reference_position = next(
            (
                str(record["posicao"])
                for record in all_records
                if record["id_atleta"] == selected_athlete and record["posicao"]
            ),
            None,
        )
    if reference_position:
        scopes.append(
            (
                f"Média {reference_position}",
                [
                    record
                    for record in period_records
                    if record["posicao"] == reference_position
                ],
            )
        )
    scopes.append(("Média do elenco", period_records))

    for scope_name, scope_records in scopes:
        cmj_average = average(
            [recorded_best(record, "cmj") for record in scope_records]
        )
        sj_average = average(
            [recorded_best(record, "sj") for record in scope_records]
        )
        if cmj_average is None and sj_average is None:
            continue
        figure.add_trace(
            go.Bar(
                name=scope_name,
                x=["CMJ", "SJ"],
                y=[cmj_average, sj_average],
            )
        )
    figure.update_layout(
        barmode="group",
        height=420,
        yaxis_title="Altura (cm)",
    )
    return figure


def evolution_chart() -> go.Figure:
    figure = go.Figure()
    if selected_athlete is not None:
        add_average_trace(
            figure,
            filtered_records,
            athlete_names[selected_athlete],
            mode="lines+markers",
        )

    reference_position = selected_position
    if selected_athlete is not None and reference_position is None:
        reference_position = next(
            (
                str(record["posicao"])
                for record in all_records
                if record["id_atleta"] == selected_athlete and record["posicao"]
            ),
            None,
        )
    if reference_position:
        add_average_trace(
            figure,
            [
                record
                for record in period_records
                if record["posicao"] == reference_position
            ],
            f"Média {reference_position}",
        )

    add_average_trace(figure, period_records, "Média do elenco")
    figure.update_layout(
        height=420,
        hovermode="x unified",
        yaxis_title="CMJ (cm)",
        xaxis_title="Data da coleta",
    )
    return figure


charts = st.columns(2)
with charts[0]:
    st.subheader("Comparativo de alturas médias")
    st.plotly_chart(comparison_chart(), width="stretch")
with charts[1]:
    st.subheader("Evolução do CMJ")
    st.plotly_chart(evolution_chart(), width="stretch")

st.caption(
    "O radar biomecânico depende de potência de pico, RSI e dados bilaterais "
    "para assimetria/simetria, que ainda não estão disponíveis."
)
