from __future__ import annotations
from collections import defaultdict
import streamlit as st
from frontend.streamlit.api_client.service_gateway import load_jump_records as gateway_load_jump_records

@st.cache_data(ttl=300, show_spinner='Carregando dados de salto...')
def load_jump_records() -> list[dict[str, object]]:
    """Carrega a view de saltos usando exclusivamente a conexão read-only."""
    return gateway_load_jump_records()

def positive_number(value: object) -> float | None:
    """Converte números positivos e trata zero como ausência de medição."""
    if value is None:
        return None
    number = float(value)
    return number if number > 0 else None

def recorded_best(record: dict[str, object], test: str) -> float | None:
    """Retorna o maior salto registrado na coluna correspondente da view."""
    return positive_number(record.get(f'maior_{test}'))
from frontend.streamlit.api_client.analytics_client import call

def average(*args, **kwargs):
    return call("jump_data.average", *args, **kwargs)

def metric_summary(*args, **kwargs):
    return call("jump_data.metric_summary", *args, **kwargs)

def build_jump_comparison(*args, **kwargs):
    return call("jump_data.build_jump_comparison", *args, **kwargs)
