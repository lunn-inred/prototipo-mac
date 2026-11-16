from __future__ import annotations
from typing import Any
import streamlit as st
from frontend.streamlit.api_client.thermal_client import summarize_pair
from frontend.streamlit.presentation.thermography_data import (
    athlete_label,
    load_thermography_athletes,
)

from frontend.streamlit.components.thermography.forms import render_forms
from frontend.streamlit.components.thermography.registration import confirm_analysis_registration
from frontend.streamlit.components.thermography.regional_summary import render_regional_summary
from frontend.streamlit.components.thermography.wizard import render_wizard, navigate

st.set_page_config(page_title="MAC Performance | Termografia", page_icon="🌡️", layout="wide")

# Estilo somente desta página; não amplia os diálogos das outras funcionalidades.
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
[data-testid="stDialog"] {
    padding-block: 1rem !important;
    overflow: hidden !important;
}
/* Streamlit: overlay > janela externa > conteúdo com role="dialog".
   Ampliar somente o role fazia o conteúdo exceder a janela externa. */
[data-testid="stDialog"] > div {
    width: min(96vw, 1600px) !important;
    max-width: calc(100vw - 2rem) !important;
    box-sizing: border-box;
}
[data-testid="stDialog"] [role="dialog"] {
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0;
    max-height: calc(100vh - 4rem);
    box-sizing: border-box;
    overflow: hidden;
    overscroll-behavior: contain;
    padding-bottom: 24px;
}
[data-testid="stDialog"] button[kind="secondary"] {
    background-color: white;
    color: #111827;
}
[data-testid="stDialog"] [data-testid="stImage"] img {
    max-width: 100%;
    object-fit: contain;
}
</style>
''')






















st.title("Termografia - Nova análise térmica")

flash_message = st.session_state.pop("thermography_flash", None)
if flash_message:
    st.success(flash_message)

try:
    athletes = load_thermography_athletes()
except Exception:
    athletes = []
    st.error("Não foi possível carregar os jogadores do banco.")

athletes_by_id = {
    int(athlete["id_atleta"]): athlete for athlete in athletes
}

editor_label_by_athlete_id = {
    athlete_id: f"{athlete_label(athlete)} — ID {athlete_id}"
    for athlete_id, athlete in athletes_by_id.items()
}
athlete_id_by_editor_label = {
    label: athlete_id for athlete_id, label in editor_label_by_athlete_id.items()
}



result = render_wizard(athletes_by_id)
if result is None:
    # st.divider()
    # render_forms(athletes, editor_label_by_athlete_id, athlete_id_by_editor_label)
    st.stop()

draft, views, items, view_metrics, pair_signature = result
selected_player_id = draft['player']
mass, pain_score, observations = draft['mass'], draft['pain'], draft['notes']

stored_metrics: dict[str, Any] = st.session_state.setdefault(
    "thermography_metrics", {}
)
if all(view_metrics.values()):
    summary = summarize_pair(view_metrics)
    front_pixels, back_pixels = summary['front']['hot_pixels'], summary['back']['hot_pixels']
    selected_player = athletes_by_id.get(selected_player_id)
    record = {
        "Jogador": (
            editor_label_by_athlete_id.get(int(selected_player_id))
            if selected_player is not None
            else None
        ),
        "Massa": mass,
        "EVA Dor": pain_score,
        "Frente": front_pixels,
        "Verso": back_pixels,
        "Observações": observations.strip(),
    }

    stored_metrics.clear()
    stored_metrics[pair_signature] = {
        "thermal_metrics": view_metrics,
        "record": record,
    }

    with st.container(border=True, key='thermal_collection_summary'):
        st.subheader("Resumo da coleta")
        with st.container(border=True):
            columns = st.columns(3)
            ids = list(athletes_by_id)
            with columns[0]:
                prepared_player_id = st.selectbox(
                    'Jogador *', ids,
                    index=ids.index(selected_player_id) if selected_player_id in ids else None,
                    format_func=lambda value: athlete_label(athletes_by_id[value]),
                    key='thermography_player',
                )
            with columns[1]:
                prepared_mass = st.number_input('Massa (kg) *', min_value=0.1,
                    value=mass, step=0.1, key='thermography_mass')
            with columns[2]:
                prepared_pain_score = st.number_input('EVA Dor *', min_value=0, max_value=10,
                    value=pain_score, step=1, key='thermography_pain_score')
        prepared_observations = st.text_area('Observações', value=observations,
                                              key='thermography_observations').strip()
        draft.update(player=prepared_player_id, mass=prepared_mass,
                     pain=prepared_pain_score, notes=prepared_observations)
        record.update(Jogador=editor_label_by_athlete_id.get(prepared_player_id),
                      Massa=prepared_mass, **{'EVA Dor': prepared_pain_score,
                                             'Observações': prepared_observations})

        missing_fields = []
        if prepared_player_id is None:
            missing_fields.append("Jogador")
        if prepared_mass is None:
            missing_fields.append("Massa")
        if prepared_pain_score is None:
            missing_fields.append("EVA Dor")

        if missing_fields:
            st.warning(
                "Preencha os campos obrigatórios antes do envio ao banco: "
                + ", ".join(missing_fields)
                + "."
            )

        regional_ready = render_regional_summary(views, items, reviewed_record={
            'player': prepared_player_id, 'mass': prepared_mass,
            'pain': prepared_pain_score, 'notes': prepared_observations,
        } if not missing_fields else None)
        already_registered = st.session_state.get('thermal_registered_analysis', {}).get('signature') == pair_signature
        if already_registered:
            st.info('Esta análise já foi registrada no banco local e na timeline. Inicie outra análise para um novo registro.')
        if st.button(
            "Registrar Análise",
            type="primary",
            disabled=bool(missing_fields) or already_registered or not regional_ready,
            key="register_thermography_analysis",
            width='stretch',
        ):
            confirm_analysis_registration(
                athlete_id=int(prepared_player_id),
                mass=prepared_mass,
                pain_score=prepared_pain_score,
                athlete_name=athletes_by_id[int(prepared_player_id)]['nome'],
                views=views,
                items=items,
                observations=prepared_observations,
                pair_signature=pair_signature,
            )
        st.caption('O registro salva as medidas no banco local e as imagens, máscaras e temperaturas na timeline.')

    navigate(6)

else:
    stored_metrics.clear()

# st.divider()
# render_forms(athletes, editor_label_by_athlete_id, athlete_id_by_editor_label)
