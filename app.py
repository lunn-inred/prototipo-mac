import streamlit as st

from ui import apply_global_style


apply_global_style()

navigation = st.navigation(
    [
        st.Page(
            "pages/Monitoramento_GPS.py",
            title="Monitoramento GPS",
            icon="📍",
            default=True,
        ),
        st.Page(
            "pages/Metricas_de_Salto.py",
            title="Métricas de Salto",
            icon="📈",
        ),
    ]
)

navigation.run()
