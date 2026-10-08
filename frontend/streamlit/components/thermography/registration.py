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
from frontend.streamlit.components.thermography.editor import LEGS, VIEW_LABELS

@st.dialog("Registrar coleta no banco")
def confirm_database_collection(
    *,
    athlete_id: int,
    mass: object,
    pain_score: object,
    front_right: object,
    front_left: object,
    back_right: object,
    back_left: object,
    observations: object,
    pair_signature: str,
) -> None:
    st.caption("Confirme a data em que esta coleta termográfica foi realizada.")
    collected_at = st.date_input(
        "Data de registro da coleta",
        value=current_sao_paulo_date(),
        key=f"database_collection_date_{pair_signature}",
    )
    if st.button(
        "Confirmar registro",
        type="primary",
        use_container_width=True,
        key=f"confirm_database_collection_{pair_signature}",
    ):
        try:
            inserted = save_image_thermography(
                athlete_id=athlete_id,
                collected_at=collected_at,
                mass=mass,
                pain_score=pain_score,
                front_right=front_right,
                front_left=front_left,
                back_right=back_right,
                back_left=back_left,
                observations=observations,
            )
        except (ValueError, RuntimeError, DuplicateThermographyError) as error:
            st.error(str(error))
        except Exception:
            st.error("Não foi possível registrar a coleta no banco.")
        else:
            load_thermography_history.clear()
            st.session_state["thermography_flash"] = (
                f"Coleta de {collected_at.strftime('%d/%m/%Y')} registrada "
                f"com {inserted} medida(s)."
            )
            st.rerun()

