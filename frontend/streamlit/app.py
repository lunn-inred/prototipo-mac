import streamlit as st
from pathlib import Path

from frontend.streamlit.components.ui import apply_global_style


apply_global_style()
PAGE_ROOT = Path(__file__).resolve().parent / 'pages'

navigation = st.navigation(
    [
        st.Page(
            PAGE_ROOT / "Jogadores.py",
            title="Jogadores",
            icon="👥",
            default=True,
        ),
        st.Page(
            PAGE_ROOT / "Monitoramento_GPS.py",
            title="Monitoramento GPS",
            icon="📍",
        ),
        st.Page(
            PAGE_ROOT / "Metricas_de_Salto.py",
            title="Métricas de Salto",
            icon="📈",
        ),
        st.Page(
            PAGE_ROOT / "Termografia.py",
            title="Termografia",
            icon="🌡️",
        ),
    ]
)

navigation.run()
