from __future__ import annotations
from collections import defaultdict
import re
import streamlit as st
from frontend.streamlit.api_client.service_gateway import load_gps_records as gateway_load_gps_records

@st.cache_data(ttl=300, show_spinner='Carregando dados de GPS...')
def load_gps_records() -> list[dict[str, object]]:
    """Carrega somente as métricas utilizadas pela página de GPS."""
    return gateway_load_gps_records()

def numeric_value(record: dict[str, object], column: str) -> float | None:
    """Converte valores não negativos e preserva zero como medição válida."""
    value = record.get(column)
    if value is None:
        return None
    number = float(value)
    return number if number >= 0 else None
from frontend.streamlit.api_client.analytics_client import call

def average(*args, **kwargs):
    return call("gps_data.average", *args, **kwargs)

def opponents_by_date(*args, **kwargs):
    return call("gps_data.opponents_by_date", *args, **kwargs)
