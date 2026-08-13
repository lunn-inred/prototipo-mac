import streamlit as st
import plotly.graph_objects as go


st.set_page_config(
    page_title="MAC Performance | Análise de Salto",
    page_icon="🔷",
    layout="wide",
    initial_sidebar_state="expanded",
)


ATHLETES = [
    "Todos os atletas", "#1 Diego", "#2 Wesley", "#3 Gabriel", "#4 Lucão",
    "#5 Felipe", "#6 Rafael", "#7 Douglas", "#8 JP", "#9 Marquinhos",
    "#10 Luan", "#11 Kauan", "#12 Rafa GK", "#13 Bruno", "#14 Caio",
    "#15 Matheus", "#16 PH", "#17 Enzo", "#18 Vini", "#19 Samuca",
    "#20 Thiaguinho", "#21 Otávio", "#22 Igor",
]
POSITIONS = ["Todas as posições", "Goleiro", "Zagueiro", "Lateral", "Volante", "Meio-campo", "Atacante"]
PERIODS = ["Últimos 7 dias", "Últimos 30 dias", "Últimos 90 dias", "Todo o histórico"]


st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;500;600;700&family=Inter:wght@400;500;600;700&display=swap');

    :root { --navy:#0b1422; --blue:#075dc9; --orange:#e17b00; --ink:#07101d; --muted:#667085; --line:#d2d8e1; --bg:#f4f6f8; }
    * { box-sizing: border-box; }
    html, body, [class*="css"] { font-family: "Inter", sans-serif; }
    .stApp { background: var(--bg); color: var(--ink); }
    #MainMenu, footer, header, [data-testid="stToolbar"] { visibility: hidden; }
    [data-testid="stAppViewContainer"] > .main { margin-left: 0; }
    .main .block-container { max-width: none; padding: 0 2rem 2.2rem; }

    [data-testid="stSidebar"] { background: var(--navy); min-width: 256px; max-width: 256px; }
    [data-testid="stSidebar"] > div:first-child { padding: 0; }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0; }
    [data-testid="stSidebarCollapseButton"], [data-testid="stSidebarNav"] { display: none; }
    .brand { height: 76px; display:flex; align-items:center; gap:14px; padding:0 22px; color:white; font-size:26px; font-weight:800; }
    .shield { width:29px; height:34px; position:relative; overflow:hidden; background:#0876dc; clip-path:polygon(50% 0,100% 12%,92% 72%,50% 100%,8% 72%,0 12%); }
    .shield:before { content:""; position:absolute; width:8px; height:48px; left:10px; top:-7px; background:#e2152d; transform:rotate(40deg); }
    .nav { padding: 7px 12px; }
    .nav-item { display:flex; align-items:center; gap:13px; height:42px; padding:0 13px; margin:2px 0; color:#d7e0ec; border-radius:9px; font-size:13px; }
    .nav-item.active { color:#fff; background:#1a283d; font-weight:700; }
    .nav-icon { display:inline-flex; width:15px; justify-content:center; color:#aeb9c8; font-size:16px; }
    .nav-item.active .nav-icon { color:#fff; }
    .nav a { color:inherit; text-decoration:none; display:block; }

    .topbar { height:53px; margin:0 -2rem; padding:0 2rem; background:#fff; border-bottom:1px solid var(--line); display:flex; align-items:center; justify-content:space-between; color:#4f5f79; font: 15px "Barlow Condensed",sans-serif; }
    .crumb-current { color:#07101d; font-weight:700; margin-left:8px; }
    .slash { color:#a6adba; margin-left:8px; }
    h1.page-title { font-size:26px; line-height:1.2; margin:25px 0 21px; font-weight:750; letter-spacing:-.5px; }

    .filters-bg { position:absolute; inset:0; border:1px solid var(--line); border-radius:15px; background:#fff; z-index:-1; }
    div[data-testid="stHorizontalBlock"]:has(.filter-anchor) { position:relative; background:#fff; border:1px solid var(--line); border-radius:15px; padding:16px 16px 14px; gap:16px; margin-bottom:24px; }
    .filter-anchor { display:none; }
    div[data-testid="stHorizontalBlock"]:has(.filter-anchor) > div:nth-child(4) { flex-grow:4; }
    [data-testid="stSelectbox"] label { font:600 13px "Barlow Condensed",sans-serif; letter-spacing:.35px; color:#586986; text-transform:uppercase; }
    [data-testid="stSelectbox"] label p { font:inherit; }
    [data-testid="stSelectbox"] > div > div { min-height:37px; border-color:#d4dae3; border-radius:8px; background:#fff; box-shadow:0 2px 3px rgba(16,24,40,.08); }
    [data-testid="stSelectbox"] [data-baseweb="select"] > div { min-height:37px; }
    [data-testid="stSelectbox"] input { font-size:14px; }

    div[data-testid="stHorizontalBlock"]:has(.metric-anchor) { gap:16px; margin-bottom:20px; }
    div[data-testid="stHorizontalBlock"]:has(.metric-anchor) > div { background:#fff; border:1px solid var(--line); border-radius:15px; padding:17px 16px 14px; min-height:99px; }
    .metric-anchor { display:none; }
    .metric-label { color:#566681; font:600 13px "Barlow Condensed",sans-serif; text-transform:uppercase; letter-spacing:.25px; }
    .metric-value { color:#030a13; font:700 25px "Inter",sans-serif; letter-spacing:-.5px; line-height:1.15; margin:3px 0 5px; }
    .metric-delta { color:#536b92; font:12px "Barlow Condensed",sans-serif; }

    div[data-testid="stHorizontalBlock"]:has(.chart-anchor) { gap:20px; align-items:stretch; }
    div[data-testid="stHorizontalBlock"]:has(.chart-anchor) > div { background:#fff; border:1px solid var(--line); border-radius:15px; padding:18px 19px 7px; min-height:466px; }
    .chart-anchor { display:none; }
    .chart-title { font-weight:700; font-size:16px; margin:3px 0 -1px; }
    [data-testid="stPlotlyChart"] { margin-top:0; }

    @media (max-width: 900px) {
      [data-testid="stSidebar"] { min-width:220px; max-width:220px; }
      .main .block-container { padding-left:1rem; padding-right:1rem; }
      .topbar { margin-left:-1rem; margin-right:-1rem; padding-left:1rem; padding-right:1rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


with st.sidebar:
    st.markdown(
        """
        <div class="brand"><span class="shield"></span><span>MAC</span></div>
        <div class="nav">
          <div class="nav-item"><span class="nav-icon">⊞</span>Mural (Visão Geral)</div>
          <div class="nav-item"><span class="nav-icon">♧</span>Perfis de Atletas</div>
          <div class="nav-item active"><span class="nav-icon">↑</span>Análise de Salto</div>
          <a href="/Monitoramento_GPS" target="_self"><div class="nav-item"><span class="nav-icon">⌁</span>Monitoramento GPS</div></a>
          <div class="nav-item"><span class="nav-icon">♨</span>Imagem Térmica</div>
          <div class="nav-item"><span class="nav-icon">◎</span>Pré-temporada</div>
          <div class="nav-item"><span class="nav-icon">∿</span>Controle de Carga</div>
          <div class="nav-item"><span class="nav-icon">⌘</span>Central de Controle</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.markdown(
    '<div class="topbar"><div>MAC Performance <span class="slash">/</span><span class="crumb-current">Análise de Salto</span></div><div>MAC Performance</div></div>',
    unsafe_allow_html=True,
)
st.markdown('<h1 class="page-title">Métricas de Salto</h1>', unsafe_allow_html=True)

filter_cols = st.columns([1.15, 0.98, 0.98, 4.5])
with filter_cols[0]:
    st.markdown('<span class="filter-anchor"></span>', unsafe_allow_html=True)
    athlete = st.selectbox("Atleta", ATHLETES, index=0)
with filter_cols[1]:
    position = st.selectbox("Posição", POSITIONS, index=0)
with filter_cols[2]:
    period = st.selectbox("Período de referência", PERIODS, index=2)

is_all = athlete == "Todos os atletas"
selected_name = athlete.split(" ", 1)[1] if not is_all else ""
selected_position = "Goleiro" if athlete in ("#1 Diego", "#12 Rafa GK") else (position if position != "Todas as posições" else "posição")

metrics = st.columns(3)
metric_values = (
    [("CMJ médio", "46.1 cm", "+ 2.3"), ("Assimetria", "4.5 %", "+ 2.7"), ("RSI", "0.00", "+ 0.22")]
    if is_all else
    [("Último CMJ", "44.6 cm", "+ 1.7"), ("Assimetria", "5.9 %", "+ 3.0"), ("RSI", "0.00", "+ 0.53")]
)
for idx, (col, item) in enumerate(zip(metrics, metric_values)):
    label, value, delta = item
    with col:
        if idx == 0:
            st.markdown('<span class="metric-anchor"></span>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="metric-delta">{delta}</div>',
            unsafe_allow_html=True,
        )


def radar_chart(individual: bool) -> go.Figure:
    categories = ["CMJ (altura)", "SJ (altura)", "Potência pico", "RSI (reatividade)", "Simetria L/R"]
    team = [78, 81, 80, 50, 96]
    position_avg = [76, 84, 78, 53, 94]
    player = [80, 88, 84, 50, 92]
    fig = go.Figure()
    if individual:
        fig.add_trace(go.Scatterpolar(
            r=player + [player[0]], theta=categories + [categories[0]], name=selected_name,
            line=dict(color="#075dc9", width=2.4), fill="toself", fillcolor="rgba(7,93,201,.17)",
            marker=dict(size=4),
        ))
        fig.add_trace(go.Scatterpolar(
            r=position_avg + [position_avg[0]], theta=categories + [categories[0]], name=f"Média {selected_position}",
            line=dict(color="#e17b00", width=1.8, dash="dash"),
        ))
    else:
        fig.add_trace(go.Scatterpolar(
            r=position_avg + [position_avg[0]], theta=categories + [categories[0]], name="Média elenco por posição",
            line=dict(color="#e17b00", width=2.1, dash="dash"),
        ))
    fig.add_trace(go.Scatterpolar(
        r=team + [team[0]], theta=categories + [categories[0]], name="Média do elenco",
        line=dict(color="#8f98a8", width=1.5, dash="dot"),
    ))
    fig.update_layout(
        height=395, margin=dict(l=65, r=65, t=50, b=35), paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Barlow Condensed", color="#61708b", size=12),
        polar=dict(
            bgcolor="rgba(0,0,0,0)", radialaxis=dict(visible=False, range=[0, 100], showticklabels=False, gridcolor="#d5dce5"),
            angularaxis=dict(gridcolor="#d5dce5", linecolor="#d5dce5"),
        ),
        legend=dict(orientation="h", x=.5, xanchor="center", y=-.08, yanchor="top", font=dict(size=12)),
        showlegend=True,
    )
    return fig


def line_chart(individual: bool) -> go.Figure:
    labels = ["Rodada 1", "Treino 1", "Rodada 2", "Treino 2", "Rodada 3", "Treino 3", "Rodada 4", "Treino 4", "Rodada 5", "Rodada 6"]
    team = [42.0, 42.3, 41.6, 40.7, 41.9, 41.8, 42.1, 41.2, 42.2, 41.7]
    position_values = [42.0, 42.1, 41.5, 40.6, 41.8, 41.7, 42.0, 41.1, 42.0, 41.6]
    player = [45.5, 41.3, 43.8, 45.0, 42.4, 46.3, 45.5, 45.6, 42.0, 44.6]
    fig = go.Figure()
    if individual:
        fig.add_trace(go.Scatter(x=labels, y=player, name=selected_name, mode="lines+markers", line=dict(color="#075dc9", width=2.5), marker=dict(size=6, color="#fff", line=dict(color="#075dc9", width=2))))
        fig.add_trace(go.Scatter(x=labels, y=position_values, name=f"Média {selected_position}", mode="lines", line=dict(color="#e17b00", width=1.8, dash="dash")))
    else:
        fig.add_trace(go.Scatter(x=labels, y=position_values, name="Média posição", mode="lines", line=dict(color="#e17b00", width=1.9, dash="dash")))
    fig.add_trace(go.Scatter(x=labels, y=team, name="Média do elenco", mode="lines", line=dict(color="#8f98a8", width=1.5, dash="dot")))
    fig.update_layout(
        height=395, margin=dict(l=8, r=5, t=24, b=48), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Barlow Condensed", color="#61708b", size=12), hovermode="x unified",
        xaxis=dict(showgrid=False, tickfont=dict(size=11), fixedrange=True),
        yaxis=dict(range=[0, 64], tickvals=[0, 15, 30, 45, 60], ticktext=["0 cm", "15 cm", "30 cm", "45 cm", "60 cm"], gridcolor="#d9dee6", griddash="dot", zeroline=False, fixedrange=True),
        legend=dict(orientation="h", x=.5, xanchor="center", y=-.08, yanchor="top", font=dict(size=12)),
    )
    return fig


chart_cols = st.columns(2)
with chart_cols[0]:
    st.markdown('<span class="chart-anchor"></span><div class="chart-title">Perfil biomecânico de salto (radar)</div>', unsafe_allow_html=True)
    st.plotly_chart(radar_chart(not is_all), width="stretch", config={"displayModeBar": False})
with chart_cols[1]:
    st.markdown('<div class="chart-title">Evolução: CMJ</div>', unsafe_allow_html=True)
    st.plotly_chart(line_chart(not is_all), width="stretch", config={"displayModeBar": False})
