import plotly.graph_objects as go
import streamlit as st


st.set_page_config(page_title="MAC Performance | Análise de Salto", page_icon="🔷", layout="wide")

ATHLETES = [
    "Todos os atletas", "#1 Diego", "#2 Wesley", "#3 Gabriel", "#4 Lucão",
    "#5 Felipe", "#6 Rafael", "#7 Douglas", "#8 JP", "#9 Marquinhos",
    "#10 Luan", "#11 Kauan", "#12 Rafa GK", "#13 Bruno", "#14 Caio",
    "#15 Matheus", "#16 PH", "#17 Enzo", "#18 Vini", "#19 Samuca",
    "#20 Thiaguinho", "#21 Otávio", "#22 Igor",
]
POSITIONS = ["Todas as posições", "Goleiro", "Zagueiro", "Lateral", "Volante", "Meio-campo", "Atacante"]
PERIODS = ["Últimos 7 dias", "Últimos 30 dias", "Últimos 90 dias", "Todo o histórico"]

st.title("Métricas de Salto")

filters = st.columns(3)
with filters[0]:
    athlete = st.selectbox("Atleta", ATHLETES)
with filters[1]:
    position = st.selectbox("Posição", POSITIONS)
with filters[2]:
    period = st.selectbox("Período de referência", PERIODS, index=2)

is_all = athlete == "Todos os atletas"
selected_name = athlete.split(" ", 1)[1] if not is_all else ""
selected_position = "Goleiro" if athlete in ("#1 Diego", "#12 Rafa GK") else (position if position != "Todas as posições" else "posição")

metric_values = (
    [("CMJ médio", "46.1 cm", "+ 2.3"), ("Assimetria", "4.5 %", "+ 2.7"), ("RSI", "0.00", "+ 0.22")]
    if is_all
    else [("Último CMJ", "44.6 cm", "+ 1.7"), ("Assimetria", "5.9 %", "+ 3.0"), ("RSI", "0.00", "+ 0.53")]
)
for column, (label, value, delta) in zip(st.columns(3), metric_values):
    column.metric(label, value, delta)


def radar_chart(individual: bool) -> go.Figure:
    categories = ["CMJ (altura)", "SJ (altura)", "Potência pico", "RSI (reatividade)", "Simetria L/R"]
    team = [78, 81, 80, 50, 96]
    position_avg = [76, 84, 78, 53, 94]
    player = [80, 88, 84, 50, 92]
    figure = go.Figure()
    if individual:
        figure.add_trace(go.Scatterpolar(r=player + [player[0]], theta=categories + [categories[0]], name=selected_name, fill="toself"))
        figure.add_trace(go.Scatterpolar(r=position_avg + [position_avg[0]], theta=categories + [categories[0]], name=f"Média {selected_position}"))
    else:
        figure.add_trace(go.Scatterpolar(r=position_avg + [position_avg[0]], theta=categories + [categories[0]], name="Média elenco por posição"))
    figure.add_trace(go.Scatterpolar(r=team + [team[0]], theta=categories + [categories[0]], name="Média do elenco"))
    figure.update_layout(
        height=420,
        paper_bgcolor="rgba(0, 0, 0, 0)",
        polar={
            "bgcolor": "rgba(0, 0, 0, 0)",
            "radialaxis": {"range": [0, 100]},
        },
    )
    return figure


def line_chart(individual: bool) -> go.Figure:
    labels = ["Rodada 1", "Treino 1", "Rodada 2", "Treino 2", "Rodada 3", "Treino 3", "Rodada 4", "Treino 4", "Rodada 5", "Rodada 6"]
    team = [42.0, 42.3, 41.6, 40.7, 41.9, 41.8, 42.1, 41.2, 42.2, 41.7]
    position_values = [42.0, 42.1, 41.5, 40.6, 41.8, 41.7, 42.0, 41.1, 42.0, 41.6]
    player = [45.5, 41.3, 43.8, 45.0, 42.4, 46.3, 45.5, 45.6, 42.0, 44.6]
    figure = go.Figure()
    if individual:
        figure.add_trace(go.Scatter(x=labels, y=player, name=selected_name, mode="lines+markers"))
        figure.add_trace(go.Scatter(x=labels, y=position_values, name=f"Média {selected_position}", mode="lines"))
    else:
        figure.add_trace(go.Scatter(x=labels, y=position_values, name="Média posição", mode="lines"))
    figure.add_trace(go.Scatter(x=labels, y=team, name="Média do elenco", mode="lines"))
    figure.update_layout(height=420, hovermode="x unified")
    figure.update_yaxes(range=[0, 64], tickvals=[0, 15, 30, 45, 60], ticktext=["0 cm", "15 cm", "30 cm", "45 cm", "60 cm"])
    return figure


charts = st.columns(2)
with charts[0]:
    st.subheader("Perfil biomecânico de salto")
    st.plotly_chart(radar_chart(not is_all), width="stretch")
with charts[1]:
    st.subheader("Evolução do CMJ")
    st.plotly_chart(line_chart(not is_all), width="stretch")
