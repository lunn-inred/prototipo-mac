import streamlit as st
import plotly.graph_objects as go


st.set_page_config(
    page_title="MAC Performance | Monitoramento GPS",
    page_icon="📍",
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
VARIABLES = [
    "Distância total (km)", "HSR — alta velocidade (m)", "Distância em sprint (m)",
    "Número de sprints (n)", "Acelerações (n)", "Desacelerações (n)", "Player load (u.a.)",
]

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;500;600;700&family=Inter:wght@400;500;600;700&display=swap');
    :root { --navy:#0b1422; --blue:#075dc9; --orange:#e17b00; --ink:#07101d; --line:#d2d8e1; --bg:#f4f6f8; }
    * { box-sizing:border-box; }
    html, body, [class*="css"] { font-family:"Inter",sans-serif; }
    .stApp { background:var(--bg); color:var(--ink); }
    #MainMenu, footer, header, [data-testid="stToolbar"] { visibility:hidden; }
    [data-testid="stSidebarNav"], [data-testid="stSidebarCollapseButton"] { display:none; }
    .main .block-container { max-width:none; padding:0 2rem 2.2rem; }
    [data-testid="stSidebar"] { background:var(--navy); min-width:256px; max-width:256px; }
    [data-testid="stSidebar"] > div:first-child { padding:0; }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap:0; }
    .brand { height:76px; display:flex; align-items:center; gap:14px; padding:0 22px; color:white; font-size:26px; font-weight:800; }
    .shield { width:29px; height:34px; position:relative; overflow:hidden; background:#0876dc; clip-path:polygon(50% 0,100% 12%,92% 72%,50% 100%,8% 72%,0 12%); }
    .shield:before { content:""; position:absolute; width:8px; height:48px; left:10px; top:-7px; background:#e2152d; transform:rotate(40deg); }
    .nav { padding:7px 12px; }
    .nav a { color:inherit; text-decoration:none; display:block; }
    .nav-item { display:flex; align-items:center; gap:13px; height:42px; padding:0 13px; margin:2px 0; color:#d7e0ec; border-radius:9px; font-size:13px; }
    .nav-item.active { color:#fff; background:#1a283d; font-weight:700; }
    .nav-icon { display:inline-flex; width:15px; justify-content:center; color:#aeb9c8; font-size:16px; }
    .nav-item.active .nav-icon { color:#fff; }
    .topbar { height:53px; margin:0 -2rem; padding:0 2rem; background:#fff; border-bottom:1px solid var(--line); display:flex; align-items:center; justify-content:space-between; color:#4f5f79; font:15px "Barlow Condensed",sans-serif; }
    .crumb-current { color:#07101d; font-weight:700; margin-left:8px; }
    .slash { color:#a6adba; margin-left:8px; }
    h1.page-title { font-size:26px; line-height:1.2; margin:25px 0 21px; font-weight:750; letter-spacing:-.5px; }

    div[data-testid="stHorizontalBlock"]:has(.filter-anchor) { position:relative; background:#fff; border:1px solid var(--line); border-radius:15px; padding:16px 16px 14px; gap:16px; margin-bottom:24px; }
    .filter-anchor,.metric-anchor,.variables-anchor,.zone-anchor { display:none; }
    div[data-testid="stHorizontalBlock"]:has(.filter-anchor) > div:nth-child(4) { flex-grow:4; }
    [data-testid="stSelectbox"] label { font:600 13px "Barlow Condensed",sans-serif; letter-spacing:.35px; color:#586986; text-transform:uppercase; }
    [data-testid="stSelectbox"] label p { font:inherit; }
    [data-testid="stSelectbox"] > div > div { min-height:37px; border-color:#d4dae3; border-radius:8px; background:#fff; box-shadow:0 2px 3px rgba(16,24,40,.08); }
    [data-testid="stSelectbox"] [data-baseweb="select"] > div { min-height:37px; }

    div[data-testid="stHorizontalBlock"]:has(.metric-anchor) { gap:16px; margin-bottom:20px; }
    div[data-testid="stHorizontalBlock"]:has(.metric-anchor) > div { background:#fff; border:1px solid var(--line); border-radius:15px; padding:17px 16px 14px; min-height:99px; }
    .metric-label { color:#566681; font:600 13px "Barlow Condensed",sans-serif; text-transform:uppercase; letter-spacing:.2px; }
    .metric-value { color:#030a13; font:700 25px "Inter",sans-serif; letter-spacing:-.5px; line-height:1.15; margin:3px 0 5px; }
    .metric-delta { color:#536b92; font:12px "Barlow Condensed",sans-serif; }

    div[data-testid="stVerticalBlockBorderWrapper"]:has(.variables-anchor),
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.zone-anchor) { background:#fff; border:1px solid var(--line); border-radius:15px; padding:13px 19px 5px; margin-bottom:20px; }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.variables-anchor) [data-testid="stVerticalBlock"],
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.zone-anchor) [data-testid="stVerticalBlock"] { gap:0; }
    .section-title { font-weight:700; font-size:16px; margin:3px 0; }
    [data-testid="stPills"] > div { justify-content:flex-end; gap:5px; }
    [data-testid="stPills"] button { min-height:27px; padding:3px 12px; border-radius:18px; border:1px solid #d5dce6; background:#fff; color:#66728b; font:12px "Barlow Condensed",sans-serif; white-space:nowrap; }
    [data-testid="stPills"] button[aria-pressed="true"] { background:#075dc9; color:white; border-color:#075dc9; }
    .empty-message { color:#6b7488; font:13px "Inter",sans-serif; padding:8px 0 10px; }

    .plot-label { color:#586986; font:600 13px "Barlow Condensed",sans-serif; text-transform:uppercase; margin:9px 0 -8px; }
    [data-testid="stPlotlyChart"] { margin-top:0; }
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
          <a href="/" target="_self"><div class="nav-item"><span class="nav-icon">↑</span>Análise de Salto</div></a>
          <div class="nav-item active"><span class="nav-icon">⌁</span>Monitoramento GPS</div>
          <div class="nav-item"><span class="nav-icon">♨</span>Imagem Térmica</div>
          <div class="nav-item"><span class="nav-icon">◎</span>Pré-temporada</div>
          <div class="nav-item"><span class="nav-icon">∿</span>Controle de Carga</div>
          <div class="nav-item"><span class="nav-icon">⌘</span>Central de Controle</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown('<div class="topbar"><div>MAC Performance <span class="slash">/</span><span class="crumb-current">Monitoramento GPS</span></div><div>MAC Performance</div></div>', unsafe_allow_html=True)
st.markdown('<h1 class="page-title">Monitoramento GPS</h1>', unsafe_allow_html=True)

filters = st.columns([1.15, .98, .98, 4.5])
with filters[0]:
    st.markdown('<span class="filter-anchor"></span>', unsafe_allow_html=True)
    athlete = st.selectbox("Atleta", ATHLETES)
with filters[1]:
    position = st.selectbox("Posição", POSITIONS)
with filters[2]:
    period = st.selectbox("Período de referência", PERIODS, index=2)

is_all = athlete == "Todos os atletas"
name = athlete.split(" ", 1)[1] if not is_all else "Média do grupo"
role = "Goleiro" if athlete in ("#1 Diego", "#12 Rafa GK") else (position if position != "Todas as posições" else "posição")

metric_data = (
    [("Distância total", "9.9 km", "+ 1.0"), ("Alta intensidade — HSR (> 20 km/h)", "591 m", "+ 124"), ("Distância em sprint (> 25 km/h)", "288 m", "+ 62"), ("Acelerações / Desacelerações", "30 / 37", "número de eventos na última sessão")]
    if is_all else
    [("Distância total", "8.5 km", "+ 0.8"), ("Alta intensidade — HSR (> 20 km/h)", "570 m", "+ 124"), ("Distância em sprint (> 25 km/h)", "149 m", "+ 45"), ("Acelerações / Desacelerações", "46 / 31", "número de eventos na última sessão")]
)
metric_cols = st.columns(4)
for idx, (col, (label, value, delta)) in enumerate(zip(metric_cols, metric_data)):
    with col:
        if idx == 0:
            st.markdown('<span class="metric-anchor"></span>', unsafe_allow_html=True)
        st.markdown(f'<div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="metric-delta">{delta}</div>', unsafe_allow_html=True)

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


def evolution_chart(variable: str) -> go.Figure:
    player_values, ticks, unit = series[variable]
    avg_role = [round(value * factor, 1) for value, factor in zip(player_values, [1.12, .94, 1.09, .81, 1.02, 1.10, .98, .92, 1.07, .96])]
    avg_team = [round(sum(player_values) / len(player_values) * factor, 1) for factor in [1.07, 1.02, .99, 1.06, 1.08, 1.05, 1.03, .98, 1.02, 1.01]]
    fig = go.Figure()
    if not is_all:
        fig.add_trace(go.Scatter(x=labels, y=player_values, name=name, mode="lines+markers", line=dict(color="#075dc9", width=2.5, shape="spline", smoothing=.65), marker=dict(size=6, color="#fff", line=dict(color="#075dc9", width=2))))
        fig.add_trace(go.Scatter(x=labels, y=avg_role, name=f"Média {role}", mode="lines", line=dict(color="#e17b00", width=1.8, dash="dash", shape="spline", smoothing=.65)))
    else:
        fig.add_trace(go.Scatter(x=labels, y=avg_role, name="Média por posição", mode="lines", line=dict(color="#e17b00", width=1.8, dash="dash", shape="spline", smoothing=.65)))
    fig.add_trace(go.Scatter(x=labels, y=avg_team, name="Média do elenco", mode="lines", line=dict(color="#8995a8", width=1.6, dash="dot", shape="spline", smoothing=.65)))
    fig.update_layout(
        height=285, margin=dict(l=6, r=5, t=20, b=35), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Barlow Condensed", color="#61708b", size=12), hovermode="x unified",
        xaxis=dict(showgrid=False, fixedrange=True, tickfont=dict(size=11)),
        yaxis=dict(range=[ticks[0], ticks[-1]], tickvals=ticks, gridcolor="#d9dee6", griddash="dot", zeroline=False, fixedrange=True, ticksuffix=f" {unit}" if unit == "km" else ""),
        legend=dict(orientation="h", x=.5, xanchor="center", y=-.08, yanchor="top", font=dict(size=12)),
    )
    return fig


with st.container(border=True):
    variable_header = st.columns([1.1, 3.4], vertical_alignment="center")
    with variable_header[0]:
        st.markdown('<span class="variables-anchor"></span><div class="section-title">Evolução de carga / intensidade</div>', unsafe_allow_html=True)
    with variable_header[1]:
        selected_variables = st.pills("Variáveis", VARIABLES, selection_mode="multi", label_visibility="collapsed", key="gps_variables")

    if not selected_variables:
        st.markdown('<div class="empty-message">Selecione ao menos uma variável.</div>', unsafe_allow_html=True)
    else:
        for variable in selected_variables:
            title = variable.upper().replace("HSR — ALTA VELOCIDADE (M)", "HSR — ALTA VELOCIDADE (M) · > 20 KM/H")
            st.markdown(f'<div class="plot-label">{title}</div>', unsafe_allow_html=True)
            st.plotly_chart(evolution_chart(variable), width="stretch", config={"displayModeBar": False}, key=f"gps_{variable}")

with st.container(border=True):
    st.markdown('<span class="zone-anchor"></span><div class="section-title">Distribuição de zonas de velocidade (média em metros)</div>', unsafe_allow_html=True)
    zone_values = [3200, 2580, 1660, 630, 260] if is_all else [3120, 2550, 1620, 650, 250]
    zone_fig = go.Figure(go.Bar(x=["Z1", "Z2", "Z3", "Z4", "Z5"], y=zone_values, name="Metros percorridos", marker_color="#0754bd", marker_line_width=0))
    zone_fig.update_traces(marker_cornerradius=7)
    zone_fig.update_layout(
        height=310, margin=dict(l=8, r=5, t=20, b=45), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Barlow Condensed", color="#61708b", size=12), bargap=.2,
        xaxis=dict(showgrid=False, fixedrange=True), yaxis=dict(range=[0, 3400], tickvals=[0, 850, 1700, 2550, 3400], gridcolor="#d9dee6", griddash="dot", zeroline=False, fixedrange=True),
        legend=dict(orientation="h", x=.5, xanchor="center", y=-.1, yanchor="top"),
    )
    st.plotly_chart(zone_fig, width="stretch", config={"displayModeBar": False})
