from statistics import pstdev

import plotly.graph_objects as go
import streamlit as st


st.set_page_config(page_title="MAC Performance | Monitoramento GPS", page_icon="📍", layout="wide")

ATHLETES = [
    "Todos os atletas", "#1 Diego", "#2 Wesley", "#3 Gabriel", "#4 Lucão",
    "#5 Felipe", "#6 Rafael", "#7 Douglas", "#8 JP", "#9 Marquinhos",
    "#10 Luan", "#11 Kauan", "#12 Rafa GK", "#13 Bruno", "#14 Caio",
    "#15 Matheus", "#16 PH", "#17 Enzo", "#18 Vini", "#19 Samuca",
    "#20 Thiaguinho", "#21 Otávio", "#22 Igor",
]
POSITIONS = ["Todas as posições", "Goleiro", "Zagueiro", "Lateral", "Volante", "Meio-campo", "Atacante"]
PERIODS = ["Últimos 7 dias", "Últimos 30 dias", "Últimos 90 dias", "Todo o histórico"]
VARIABLES = [
    "Distância total (km)", "HSR — alta velocidade (m)", "Distância em sprint (m)",
    "Número de sprints (n)", "Acelerações (n)", "Desacelerações (n)", "Player load (u.a.)",
]

st.title("Monitoramento GPS")

filters = st.columns(3)
with filters[0]:
    athlete = st.selectbox("Atleta", ATHLETES)
with filters[1]:
    position = st.selectbox("Posição", POSITIONS)
with filters[2]:
    period = st.selectbox("Período de referência", PERIODS, index=2)

is_all = athlete == "Todos os atletas"
name = athlete.split(" ", 1)[1] if not is_all else "Média do grupo"
role = "Goleiro" if athlete in ("#1 Diego", "#12 Rafa GK") else (position if position != "Todas as posições" else "posição")

labels = ["Rodada 1", "Treino 1", "Rodada 2", "Treino 2", "Rodada 3", "Treino 3", "Rodada 4", "Treino 4", "Rodada 5", "Rodada 6"]
series = {
    "Distância total (km)": ([8.3, 8.3, 8.0, 8.2, 9.8, 8.2, 10.3, 10.1, 8.5, 8.5], [0, 3, 6, 9, 12], "km"),
    "HSR — alta velocidade (m)": ([630, 720, 460, 800, 680, 540, 510, 350, 620, 570], [0, 200, 400, 600, 800], "m"),
    "Distância em sprint (m)": ([170, 205, 110, 260, 195, 145, 180, 92, 205, 149], [0, 75, 150, 225, 300], "m"),
    "Número de sprints (n)": ([14, 17, 10, 21, 18, 12, 16, 9, 19, 15], [0, 6, 12, 18, 24], "n"),
    "Acelerações (n)": ([38, 42, 31, 49, 45, 36, 44, 29, 51, 46], [0, 15, 30, 45, 60], "n"),
    "Desacelerações (n)": ([28, 35, 24, 38, 34, 29, 37, 21, 40, 31], [0, 10, 20, 30, 40], "n"),
    "Player load (u.a.)": ([510, 570, 460, 630, 590, 480, 610, 420, 575, 550], [0, 200, 400, 600, 800], "u.a."),
}


def series_standard_deviation(variable: str) -> float:
    values, _, _ = series[variable]
    return pstdev(values)


metric_values = (
    ["9.9 km", "591 m", "288 m", "30 / 37"]
    if is_all
    else ["8.5 km", "570 m", "149 m", "46 / 31"]
)
metric_data = [
    (
        "Distância total",
        metric_values[0],
        f"± {series_standard_deviation('Distância total (km)'):.1f} km",
    ),
    (
        "Alta intensidade — HSR (> 20 km/h)",
        metric_values[1],
        f"± {series_standard_deviation('HSR — alta velocidade (m)'):.1f} m",
    ),
    (
        "Distância em sprint (> 25 km/h)",
        metric_values[2],
        f"± {series_standard_deviation('Distância em sprint (m)'):.1f} m",
    ),
    (
        "Acelerações / Desacelerações",
        metric_values[3],
        "eventos na última sessão",
    ),
]

for column, (label, value, standard_deviation) in zip(st.columns(4), metric_data):
    with column:
        st.metric(label, value)
        st.caption(standard_deviation)


def evolution_chart(variable: str) -> go.Figure:
    player_values, ticks, unit = series[variable]
    role_factors = [1.12, 0.94, 1.09, 0.81, 1.02, 1.10, 0.98, 0.92, 1.07, 0.96]
    team_factors = [1.07, 1.02, 0.99, 1.06, 1.08, 1.05, 1.03, 0.98, 1.02, 1.01]
    avg_role = [round(value * factor, 1) for value, factor in zip(player_values, role_factors)]
    average = sum(player_values) / len(player_values)
    avg_team = [round(average * factor, 1) for factor in team_factors]
    figure = go.Figure()
    if not is_all:
        figure.add_trace(go.Scatter(x=labels, y=player_values, name=name, mode="lines+markers"))
        figure.add_trace(go.Scatter(x=labels, y=avg_role, name=f"Média {role}", mode="lines"))
    else:
        figure.add_trace(go.Scatter(x=labels, y=avg_role, name="Média por posição", mode="lines"))
    figure.add_trace(go.Scatter(x=labels, y=avg_team, name="Média do elenco", mode="lines"))
    figure.update_layout(height=320, hovermode="x unified")
    figure.update_yaxes(range=[ticks[0], ticks[-1]], tickvals=ticks, ticksuffix=f" {unit}" if unit == "km" else "")
    return figure


st.subheader("Evolução de carga e intensidade")
selected_variables = st.multiselect("Variáveis", VARIABLES)

if not selected_variables:
    st.info("Selecione ao menos uma variável.")
else:
    for variable in selected_variables:
        st.markdown(f"#### {variable}")
        st.plotly_chart(evolution_chart(variable), width="stretch", key=f"gps_{variable}")

st.subheader("Distribuição de zonas de velocidade")
zone_values = [3200, 2580, 1660, 630, 260] if is_all else [3120, 2550, 1620, 650, 250]
zone_figure = go.Figure(go.Bar(x=["Z1", "Z2", "Z3", "Z4", "Z5"], y=zone_values, name="Metros percorridos"))
zone_figure.update_layout(height=340)
zone_figure.update_yaxes(range=[0, 3400], tickvals=[0, 850, 1700, 2550, 3400])
st.plotly_chart(zone_figure, width="stretch")
