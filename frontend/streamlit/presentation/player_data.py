from __future__ import annotations
from collections import defaultdict
from datetime import date
import streamlit as st
from frontend.streamlit.api_client.service_gateway import load_player_dashboard
METRIC_NAMES = {'maior_cmj': 'cmj', 'distance (km)': 'distance', 'eva': 'eva', 'eva dor': 'eva', 'eva_dor': 'eva'}

@st.cache_data(ttl=300, show_spinner='Carregando dados dos jogadores...')
def load_player_dashboard_data() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Carrega cadastro e medidas usando exclusivamente a conexão read-only."""
    return load_player_dashboard()

def player_name(athlete: dict[str, object]) -> str:
    """Retorna o nome mais curto disponível para apresentação."""
    nickname = str(athlete.get('apelido') or '').strip()
    name = str(athlete.get('nome') or '').strip()
    return nickname or name or f"Jogador {athlete['id_atleta']}"
from frontend.streamlit.api_client.analytics_client import call

def group_measurements(*args, **kwargs):
    return call("player_data.group_measurements", *args, **kwargs)

def metric_summary(*args, **kwargs):
    return call("player_data.metric_summary", *args, **kwargs)

def latest_eva(*args, **kwargs):
    return call("player_data.latest_eva", *args, **kwargs)

def eva_classification(*args, **kwargs):
    return call("player_data.eva_classification", *args, **kwargs)
