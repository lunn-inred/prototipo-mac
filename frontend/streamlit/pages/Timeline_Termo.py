"""Consulta e comparação das análises térmicas armazenadas localmente."""

import streamlit as st

from frontend.streamlit.components.thermography.timeline import render_timeline
from frontend.streamlit.presentation.thermography_data import load_thermography_athletes

st.set_page_config(page_title="MAC Performance | Timeline térmica", page_icon="🗓️", layout="wide")
st.html('''
<style>
[data-testid="stMainBlockContainer"] [data-testid="stImage"] {
    width: fit-content !important;
}
[data-testid="stMainBlockContainer"] [data-testid="stImage"] img {
    max-height: min(40vh, 400px);
    max-width: 100%;
    width: auto;
    object-fit: contain;
}
</style>
''')

st.title("Timeline térmica")

try:
    athletes = load_thermography_athletes()
except Exception:
    st.error("Não foi possível carregar os jogadores do banco.")
    st.stop()

render_timeline(athletes)
