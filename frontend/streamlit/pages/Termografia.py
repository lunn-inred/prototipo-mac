from __future__ import annotations
import hashlib
import io
from datetime import date
from typing import Any
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError
from streamlit_drawable_konva import crop_box_from_json, st_canvas
from frontend.streamlit.api_client.contracts import (unique_matching_athlete_id)
from frontend.streamlit.api_client.thermal_client import (annotate_boxes, compare_hot_masks, count_hot_pixels, detect_colorbar_box, detect_leg_boxes, hot_pixels_overlay, segmentation_overlay, segment_leg_mask, temperature_matrix, DEFAULT_PART_CUTS, LEG_PARTS, leg_part_metrics, scale_percentage_from_temperature, temperature_from_scale_percentage)
from frontend.streamlit.presentation.thermography_data import (
    athlete_label,
    load_thermography_athletes,
    load_thermography_history,
)
from frontend.streamlit.api_client.contracts import (DuplicateThermographyError, LegacyThermographyRecord, current_sao_paulo_date)
from frontend.streamlit.api_client.service_gateway import (
    extract_thermography_scale,
    extract_legacy_documents,
    save_image_thermography,
    save_legacy_thermography,
)
from frontend.streamlit.components.thermography.editor import *

from frontend.streamlit.components.thermography.timeline import render_timeline, confirm_timeline_date
from frontend.streamlit.components.thermography.forms import render_forms
from frontend.streamlit.components.thermography.registration import confirm_database_collection

st.set_page_config(page_title="MAC Performance | Termografia", page_icon="🌡️", layout="wide")





















st.title("Termografia")

flash_message = st.session_state.pop("thermography_flash", None)
if flash_message:
    st.success(flash_message)

try:
    athletes = load_thermography_athletes()
except Exception as error:
    athletes = []
    st.error("Não foi possível carregar os jogadores do banco.")

athletes_by_id = {
    int(athlete["id_atleta"]): athlete for athlete in athletes
}
athlete_ids = list(athletes_by_id)

editor_label_by_athlete_id = {
    athlete_id: f"{athlete_label(athlete)} — ID {athlete_id}"
    for athlete_id, athlete in athletes_by_id.items()
}
athlete_id_by_editor_label = {
    label: athlete_id for athlete_id, label in editor_label_by_athlete_id.items()
}



st.subheader("Nova análise térmica")
st.caption(
    "Informe os dados da coleta e envie em conjunto as imagens de frente e verso."
)

with st.container(border=True):
    record_columns = st.columns(3)
    with record_columns[0]:
        selected_player_id = st.selectbox(
            "Jogador *",
            athlete_ids,
            index=None,
            placeholder=(
                "Selecione um jogador"
                if athlete_ids
                else "Nenhum jogador disponível"
            ),
            format_func=lambda athlete_id: athlete_label(
                athletes_by_id[athlete_id]
            ),
            disabled=not athlete_ids,
            key="thermography_player",
        )
    with record_columns[1]:
        mass = st.number_input(
            "Massa (kg) *",
            min_value=0.1,
            value=None,
            step=0.1,
            format="%.1f",
            placeholder="Informe a massa",
            key="thermography_mass",
        )
    with record_columns[2]:
        pain_score = st.number_input(
            "EVA Dor *",
            min_value=0,
            max_value=10,
            value=None,
            step=1,
            placeholder="Valor de 0 a 10",
            key="thermography_pain_score",
        )
    observations = st.text_area(
        "Observações",
        placeholder="Campo opcional",
        key="thermography_observations",
    )
    st.caption("* Campos obrigatórios para o envio ao banco.")

render_timeline(selected_player_id)

upload_columns = st.columns(2)
with upload_columns[0]:
    front_upload = st.file_uploader(
        "Imagem de frente",
        type=["png", "jpg", "jpeg"],
        help="Imagem HIKMICRO frontal com as caixas R1 e R2 visíveis.",
        key="thermography_front_upload",
    )
with upload_columns[1]:
    back_upload = st.file_uploader(
        "Imagem do verso",
        type=["png", "jpg", "jpeg"],
        help="Imagem HIKMICRO do verso (costas) com as caixas R1 e R2 visíveis.",
        key="thermography_back_upload",
    )

if not front_upload or not back_upload:
    st.session_state.pop("thermography_metrics", None)
    missing = []
    if not front_upload:
        missing.append("frente")
    if not back_upload:
        missing.append("verso")
    st.info(f"Envie a imagem de {' e '.join(missing)} para iniciar a análise.")
    st.divider()
    render_forms(athletes, editor_label_by_athlete_id, athlete_id_by_editor_label)
    st.stop()

uploads = {"front": front_upload, "back": back_upload}
views: dict[str, dict[str, Any]] = {}
for view_key, uploaded in uploads.items():
    content = uploaded.getvalue()
    try:
        image = load_thermography(content)
    except ValueError as error:
        st.error(f"{VIEW_LABELS[view_key]} — {uploaded.name}: {error}")
        continue
    views[view_key] = {
        "name": uploaded.name,
        "content": content,
        "image": image,
        "signature": image_signature(content),
    }

if len(views) != 2:
    st.divider()
    render_forms(athletes, editor_label_by_athlete_id, athlete_id_by_editor_label)
    st.stop()

if views["front"]["signature"] == views["back"]["signature"]:
    st.warning("A mesma imagem foi selecionada para frente e verso. Confira os arquivos.")

pair_signature = hashlib.sha256(
    (views["front"]["signature"] + views["back"]["signature"]).encode()
).hexdigest()
items: dict[str, dict[str, Any]] = st.session_state.setdefault(
    "thermography_items", {}
)
active_item_keys = {
    f"{view_key}:{view['signature']}" for view_key, view in views.items()
}
for view_key, view in views.items():
    item_key = f"{view_key}:{view['signature']}"
    if item_key in items:
        continue
    try:
        detected_scale = cached_temperature_scale(view["content"])
    except ValueError as error:
        items[item_key] = {
            "minimum_temperature": DEFAULT_MIN_TEMPERATURE,
            "maximum_temperature": DEFAULT_MAX_TEMPERATURE,
            "scale_detected": False,
            "scale_error": str(error),
        }
    else:
        items[item_key] = {
            **detected_scale,
            "scale_detected": True,
        }
for item_key in set(items) - active_item_keys:
    del items[item_key]

st.info(
    "A lateralidade é invertida automaticamente entre as vistas de frente e verso."
)
st.warning(
    "Conversão experimental: a paleta é estimada pela barra térmica lateral "
    "presente em cada imagem."
)

selected_threshold_mode = st.session_state.setdefault(
    THRESHOLD_MODE_KEY, PERCENTAGE_MODE
)
for view_key in VIEW_LABELS:
    st.session_state.setdefault(
        threshold_mode_key(view_key), selected_threshold_mode
    )

tabs = st.tabs(["Frente", "Verso"])
view_metrics: dict[str, dict[str, dict[str, float | int]] | None] = {}
for tab, view_key in zip(tabs, ("front", "back")):
    view = views[view_key]
    item_key = f"{view_key}:{view['signature']}"
    with tab:
        view_metrics[view_key] = render_view(
            view_key,
            view["name"],
            view["content"],
            view["image"],
            items[item_key],
            item_key,
        )

stored_metrics: dict[str, Any] = st.session_state.setdefault(
    "thermography_metrics", {}
)
if all(view_metrics.values()):
    from frontend.streamlit.api_client.thermal_client import summarize_pair
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
