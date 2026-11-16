import streamlit as st
from pathlib import Path

from frontend.streamlit.components.ui import apply_global_style
from frontend.streamlit.google_login import (
    authenticated, enabled, render_login, render_logout, restore_session,
)


restore_session()
login_required = enabled() and not authenticated()
apply_global_style(show_sidebar_logo=not login_required)
PAGE_ROOT = Path(__file__).resolve().parent / 'pages'

if login_required:
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
