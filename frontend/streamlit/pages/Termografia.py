from __future__ import annotations
from typing import Any
import pandas as pd
import streamlit as st
from frontend.streamlit.api_client.thermal_client import summarize_pair
from frontend.streamlit.presentation.thermography_data import (
    athlete_label,
    load_thermography_athletes,
)

from frontend.streamlit.components.thermography.forms import render_forms
from frontend.streamlit.components.thermography.save_flow import render_pending_save
from frontend.streamlit.components.thermography.draft_state import reset_after_saved_analysis
from frontend.streamlit.components.thermography.wizard import render_wizard, navigate

st.set_page_config(page_title="MAC Performance | Termografia", page_icon="🌡️", layout="wide")
reset_after_saved_analysis()
if sync := st.session_state.pop('thermal_metadata_sync', None):
    st.session_state.update(sync['updates'])
    st.session_state.pop(sync['editor'], None)

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






















st.title('Termografia - Editar análise térmica' if st.session_state.get('thermal_edit_source') or st.session_state.get('thermal_saved_draft') else 'Termografia - Nova análise térmica')
if source := st.session_state.get('thermal_edit_source'):
    st.caption(f'Editando análise de {source["collected_at"]:%d/%m/%Y}. As alterações só serão gravadas ao salvar.')

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
    render_pending_save()
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
    front_area, back_area = summary['front']['total_pixels'], summary['back']['total_pixels']
    front_percentage, back_percentage = summary['front']['hot_percentage'], summary['back']['hot_percentage']
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
        "Data da coleta": draft.get('collected_at'),
    }

    stored_metrics.clear()
    stored_metrics[pair_signature] = {
        "thermal_metrics": view_metrics,
        "record": record,
    }

    with st.container(border=True, key='thermal_collection_summary'):
        st.subheader("Resumo da coleta")
        summary_columns = st.columns(2)
        with summary_columns[0]:
            with st.container(border=True):
                st.metric(
                    "Pixels quentes — Frente (duas pernas)",
                    f"{front_pixels:,} px".replace(",", "."),
                )
                st.caption(
                    f"{front_percentage:.1f}% quentes · área segmentada: "
                    f"{front_area:,} pixels".replace(",", ".")
                )
        with summary_columns[1]:
            with st.container(border=True):
                st.metric(
                    "Pixels quentes — Costas (duas pernas)",
                    f"{back_pixels:,} px".replace(",", "."),
                )
                st.caption(
                    f"{back_percentage:.1f}% quentes · área segmentada: "
                    f"{back_area:,} pixels".replace(",", ".")
                )

        st.caption(
            "Edite Jogador, Massa, EVA Dor, Data da coleta e Observações diretamente na tabela. "
            "Frente e Costas são calculados automaticamente."
        )
        prepared_frame = pd.DataFrame([record])[['Jogador', 'Data da coleta', 'Massa', 'EVA Dor', 'Frente', 'Verso', 'Observações']]
        prepared_frame["Jogador"] = prepared_frame["Jogador"].astype("string")
        prepared_frame["Massa"] = pd.to_numeric(
            prepared_frame["Massa"], errors="coerce"
        ).astype("Float64")
        prepared_frame["EVA Dor"] = pd.to_numeric(
            prepared_frame["EVA Dor"], errors="coerce"
        ).astype("Int64")
        prepared_frame["Frente"] = prepared_frame["Frente"].astype("Int64")
        prepared_frame["Verso"] = prepared_frame["Verso"].astype("Int64")
        prepared_frame["Observações"] = (
            prepared_frame["Observações"].fillna("").astype("string")
        )
        prepared_frame['Data da coleta'] = pd.to_datetime(prepared_frame['Data da coleta']).dt.date
        edited_prepared_frame = st.data_editor(
            prepared_frame,
            width="stretch",
            hide_index=True,
            num_rows="fixed",
            disabled=["Frente", "Verso"],
            column_config={
                'Data da coleta': st.column_config.DateColumn(format='DD/MM/YYYY', required=True),
                "Jogador": st.column_config.SelectboxColumn(
                    options=sorted(athlete_id_by_editor_label),
                    required=True,
                ),
                "Massa": st.column_config.NumberColumn(
                    min_value=0.1,
                    step=0.1,
                    format="%.1f kg",
                    required=True,
                ),
                "EVA Dor": st.column_config.NumberColumn(
                    min_value=0,
                    max_value=10,
                    step=1,
                    format="%d",
                    required=True,
                ),
                "Frente": st.column_config.NumberColumn(format="%d"),
                "Verso": st.column_config.NumberColumn("Costas", format="%d"),
                "Observações": st.column_config.TextColumn(
                    width="large",
                    default="",
                ),
            },
            key=f"thermography_record_editor_{pair_signature}",
        )
        prepared_record = edited_prepared_frame.iloc[0].to_dict()
        prepared_player_id = athlete_id_by_editor_label.get(
            prepared_record.get("Jogador")
        )
        prepared_mass = prepared_record.get("Massa")
        prepared_pain_score = prepared_record.get("EVA Dor")
        prepared_day = prepared_record.get('Data da coleta')
        prepared_day = pd.to_datetime(prepared_day).date() if prepared_day is not None and not pd.isna(prepared_day) else None
        prepared_mass = None if prepared_mass is None or pd.isna(prepared_mass) else float(prepared_mass)
        prepared_pain_score = None if prepared_pain_score is None or pd.isna(prepared_pain_score) else int(prepared_pain_score)
        prepared_observations = prepared_record.get("Observações")
        if prepared_observations is None or pd.isna(prepared_observations):
            prepared_observations = ""
        else:
            prepared_observations = str(prepared_observations).strip()

        missing_fields = []
        if prepared_day is None:
            missing_fields.append('Data da coleta')
        if prepared_player_id is None:
            missing_fields.append("Jogador")
        if prepared_mass is None or pd.isna(prepared_mass):
            missing_fields.append("Massa")
        if prepared_pain_score is None or pd.isna(prepared_pain_score):
            missing_fields.append("EVA Dor")

        if missing_fields:
            st.warning(
                "Preencha os campos obrigatórios antes do envio ao banco: "
                + ", ".join(missing_fields)
                + "."
            )
        else:
            st.success("Registro pronto para envio. Observações permanece opcional.")

        draft.update(player=prepared_player_id, mass=prepared_mass, pain=prepared_pain_score,
                     notes=prepared_observations, collected_at=prepared_day)
        st.session_state.update(thermography_player=prepared_player_id, thermography_mass=prepared_mass,
            thermography_pain_score=prepared_pain_score, thermography_observations=prepared_observations)
        st.session_state['thermal_prepared_record'] = dict(athlete_id=prepared_player_id,
            athlete_name=athletes_by_id.get(prepared_player_id, {}).get('nome', ''), mass=prepared_mass,
            pain_score=prepared_pain_score, observations=prepared_observations, collected_at=prepared_day,
            views=views, items=items, pair_signature=pair_signature)
        st.caption('Use Salvar análise abaixo. Se houver dados incompletos, será salvo um rascunho mediante confirmação.')

    navigate(6)
    render_pending_save()

else:
    stored_metrics.clear()

# st.divider()
# render_forms(athletes, editor_label_by_athlete_id, athlete_id_by_editor_label)
