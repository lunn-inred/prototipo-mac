import streamlit as st
from pathlib import Path

from frontend.streamlit.components.ui import apply_global_style
from frontend.streamlit.google_login import (
    authenticated, enabled, render_login, render_logout, restore_session,
)


apply_global_style()
restore_session()
PAGE_ROOT = Path(__file__).resolve().parent / 'pages'

if enabled() and not authenticated():
    navigation = st.navigation(
        [st.Page(render_login, title="Entrar", icon="🔐", default=True)],
        position="hidden",
    )
else:
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
                title="Monitoramento Salto",
                icon="📈",
            ),
            st.Page(
                PAGE_ROOT / "Termografia.py",
                title="Termografia",
                icon="🌡️",
            ),
            st.Page(
                PAGE_ROOT / "Timeline_Termo.py",
                title="Timeline térmica",
                icon="🗓️",
            ),
        ]
    )
    render_logout()

navigation.run()
