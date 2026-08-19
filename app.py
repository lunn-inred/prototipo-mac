import streamlit as st


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
