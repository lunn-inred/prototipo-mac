from __future__ import annotations
from typing import Any
import pandas as pd
import streamlit as st
from frontend.streamlit.api_client.thermal_client import summarize_pair
from frontend.streamlit.presentation.thermography_data import (
    athlete_label,
    load_thermography_athletes,
)

from frontend.streamlit.components.thermography.timeline import render_timeline, confirm_timeline_date
from frontend.streamlit.components.thermography.forms import render_forms
from frontend.streamlit.components.thermography.registration import confirm_database_collection
from frontend.streamlit.components.thermography.wizard import render_wizard

st.set_page_config(page_title="MAC Performance | Termografia", page_icon="🌡️", layout="wide")





















st.title("Termografia")

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



with st.expander('Timeline térmica da sessão', expanded=False):
    render_timeline(st.session_state.get('thermal_draft', {}).get('player'))

result = render_wizard(athletes_by_id)
if result is None:
    st.divider()
    render_forms(athletes, editor_label_by_athlete_id, athlete_id_by_editor_label)
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
    }

    stored_metrics.clear()
    stored_metrics[pair_signature] = {
        "thermal_metrics": view_metrics,
        "record": record,
    }

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
                "Pixels quentes — Verso (duas pernas)",
                f"{back_pixels:,} px".replace(",", "."),
            )
            st.caption(
                f"{back_percentage:.1f}% quentes · área segmentada: "
                f"{back_area:,} pixels".replace(",", ".")
            )

    if st.button(
        "Adicionar à timeline",
        disabled=selected_player_id is None,
        help=(
            "Selecione um jogador para adicionar esta análise."
            if selected_player_id is None
            else "Mantém imagens e métricas somente durante esta sessão."
        ),
        key=f"add_thermography_timeline_{pair_signature}",
        width='stretch',
    ):
        confirm_timeline_date(
            int(selected_player_id), views, items, pair_signature
        )

    st.subheader("Registro preparado")
    st.caption(
        "Edite Jogador, Massa, EVA Dor e Observações diretamente na tabela. "
        "Frente e Verso são calculados automaticamente."
    )
    prepared_frame = pd.DataFrame([record])
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
    edited_prepared_frame = st.data_editor(
        prepared_frame,
        width="stretch",
        hide_index=True,
        num_rows="fixed",
        disabled=["Frente", "Verso"],
        column_config={
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
            "Verso": st.column_config.NumberColumn(format="%d"),
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
    prepared_observations = prepared_record.get("Observações")
    if prepared_observations is None or pd.isna(prepared_observations):
        prepared_observations = ""
    else:
        prepared_observations = str(prepared_observations).strip()

    missing_fields = []
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

    if st.button(
        "Registrar coleta no banco",
        type="primary",
        disabled=bool(missing_fields),
        key="save_image_thermography",
        width='stretch',
    ):
        confirm_database_collection(
            athlete_id=int(prepared_player_id),
            mass=prepared_mass,
            pain_score=prepared_pain_score,
            front_right=view_metrics["front"]["right"]["hot_pixels"],
            front_left=view_metrics["front"]["left"]["hot_pixels"],
            back_right=view_metrics["back"]["right"]["hot_pixels"],
            back_left=view_metrics["back"]["left"]["hot_pixels"],
            observations=prepared_observations,
            pair_signature=pair_signature,
        )
    st.caption("As imagens não são armazenadas; somente as medidas são enviadas.")
else:
    stored_metrics.clear()

st.divider()
render_forms(athletes, editor_label_by_athlete_id, athlete_id_by_editor_label)
