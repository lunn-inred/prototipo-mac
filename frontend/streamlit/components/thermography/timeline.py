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

def _timeline_sort_key(entry: dict[str, Any]) -> tuple[date, int]:
    return entry["collected_at"], int(entry["sequence"])


def _timeline_entry_by_id(entry_id: int | None) -> dict[str, Any] | None:
    if entry_id is None:
        return None
    return next(
        (
            entry
            for entry in st.session_state.get("thermography_timeline", [])
            if int(entry["id"]) == int(entry_id)
        ),
        None,
    )


def _select_timeline_entry(entry: dict[str, Any], role: str) -> None:
    """Seleciona Basal ou Atual sem modificar a outra ponta da comparação."""
    st.session_state[f"thermography_timeline_{role}"] = int(entry["id"])


def _select_timeline_entry_by_id(entry_id: int, role: str) -> None:
    """Callback de botão: atualiza a seleção antes do rerun do Streamlit."""
    entry = _timeline_entry_by_id(entry_id)
    if entry is None:
        st.session_state["thermography_timeline_message"] = (
            "A coleta selecionada não está mais disponível na sessão."
        )
        return
    _select_timeline_entry(entry, role)


def _timeline_view_at_threshold(source, threshold):
    from frontend.streamlit.api_client.thermal_client import timeline_view_at_threshold
    return timeline_view_at_threshold(source, threshold)


def _render_comparison(t0: dict[str, Any], ti: dict[str, Any]) -> None:
    st.markdown("#### Comparação Basal × Atual")
    st.caption(
        f"Basal: {t0['collected_at'].strftime('%d/%m/%Y')} · "
        f"Atual: {ti['collected_at'].strftime('%d/%m/%Y')}"
    )
    tabs = st.tabs(["Frente", "Verso"])
    for tab, view_key in zip(tabs, ("front", "back")):
        with tab:
            baseline_source = t0["views"][view_key]
            current_source = ti["views"][view_key]
            threshold_columns = st.columns(2)
            with threshold_columns[0]:
                baseline_threshold = st.slider(
                    "Limiar da coleta basal (°C)",
                    min_value=float(baseline_source["minimum_temperature"]),
                    max_value=float(baseline_source["maximum_temperature"]),
                    value=float(baseline_source["default_threshold"]),
                    step=max(
                        (
                            float(baseline_source["maximum_temperature"])
                            - float(baseline_source["minimum_temperature"])
                        ) / 200,
                        0.01,
                    ),
                    key=f"timeline_threshold_t0_{t0['id']}_{view_key}",
                )
            with threshold_columns[1]:
                current_threshold = st.slider(
                    "Limiar da coleta atual (°C)",
                    min_value=float(current_source["minimum_temperature"]),
                    max_value=float(current_source["maximum_temperature"]),
                    value=float(current_source["default_threshold"]),
                    step=max(
                        (
                            float(current_source["maximum_temperature"])
                            - float(current_source["minimum_temperature"])
                        ) / 200,
                        0.01,
                    ),
                    key=f"timeline_threshold_ti_{ti['id']}_{view_key}",
                )
            st.caption(
                "O mapa e todas as métricas abaixo são recalculados imediatamente "
                "quando um dos limiares é alterado."
            )
            baseline = _timeline_view_at_threshold(
                baseline_source, baseline_threshold
            )
            current = _timeline_view_at_threshold(
                current_source, current_threshold
            )
            t0_column, ti_column, map_column, metrics_column = st.columns(
                [1.1, 1.1, 1.4, 1.2], gap="medium"
            )
            with t0_column:
                st.markdown("##### Basal")
                st.image(baseline["image"], width="stretch")
            with ti_column:
                st.markdown("##### Atual")
                st.image(current["image"], width="stretch")
            with map_column:
                st.markdown("##### Mapa comparativo")
                map_columns = st.columns(2)
                for column, (label, side) in zip(map_columns, LEGS.items()):
                    comparison = compare_hot_masks(
                        baseline["hot_masks"][side],
                        current["hot_masks"][side],
                        baseline["boxes"][side],
                        current["boxes"][side],
                    )
                    with column:
                        st.image(comparison["image"], caption=label, width="stretch")
                        compared_total = sum(
                            int(comparison[key])
                            for key in (
                                "new_pixels", "persistent_pixels", "resolved_pixels"
                            )
                        )
                        def category_value(key: str) -> str:
                            value = int(comparison[key])
                            percentage = value / compared_total * 100 if compared_total else 0.0
                            return f"{value:,} ({percentage:.1f}%)"
                        st.caption(
                            f"Novos: {category_value('new_pixels')} · "
                            f"Persistentes: {category_value('persistent_pixels')} · "
                            f"Resolvidos: {category_value('resolved_pixels')}"
                        )
                st.caption(
                    "Vermelho: novos · Amarelo: persistentes · Azul: resolvidos"
                )
            with metrics_column:
                st.markdown("##### Métricas atuais")
                st.caption(
                    f"Tmin {current['minimum_temperature']:.1f} °C · "
                    f"Tmax {current['maximum_temperature']:.1f} °C · "
                    f"limiar {current['threshold']:.1f} °C"
                )
                current_hot_total = sum(
                    int(current["metrics"][side]["hot_pixels"])
                    for side in LEGS.values()
                )
                baseline_hot_total = sum(
                    int(baseline["metrics"][side]["hot_pixels"])
                    for side in LEGS.values()
                )
                current_area_total = sum(
                    int(current["metrics"][side]["total_pixels"])
                    for side in LEGS.values()
                )
                baseline_area_total = sum(
                    int(baseline["metrics"][side]["total_pixels"])
                    for side in LEGS.values()
                )
                current_view_percentage = current_hot_total / current_area_total * 100
                baseline_view_percentage = baseline_hot_total / baseline_area_total * 100
                st.metric(
                    "Total da vista",
                    f"{current_hot_total:,} px".replace(",", "."),
                    delta=f"{current_hot_total - baseline_hot_total:+,} px".replace(",", "."),
                )
                st.caption(
                    f"{current_view_percentage:.1f}% "
                    f"({current_view_percentage - baseline_view_percentage:+.1f} p.p.)"
                )
                for label, side in LEGS.items():
                    current_metric = current["metrics"][side]
                    baseline_metric = baseline["metrics"][side]
                    hot_delta = int(current_metric["hot_pixels"]) - int(
                        baseline_metric["hot_pixels"]
                    )
                    percentage_delta = float(current_metric["hot_percentage"]) - float(
                        baseline_metric["hot_percentage"]
                    )
                    st.metric(
                        f"Pixels quentes — {label}",
                        f"{int(current_metric['hot_pixels']):,} px".replace(",", "."),
                        delta=f"{hot_delta:+,} px".replace(",", "."),
                    )
                    st.caption(
                        f"{float(current_metric['hot_percentage']):.1f}% "
                        f"({percentage_delta:+.1f} p.p.) · área: "
                        f"{int(current_metric['total_pixels']):,} px".replace(",", ".")
                    )


def render_timeline(selected_player_id: int | None) -> None:
    st.subheader("Timeline térmica")
    if message := st.session_state.pop("thermography_timeline_message", None):
        st.warning(message)
    if selected_player_id is None:
        st.caption("Selecione um jogador para visualizar e comparar suas coletas da sessão.")
        return

    timeline_entries = st.session_state.get("thermography_timeline", [])
    if any(entry.get("version") != 2 for entry in timeline_entries):
        timeline_entries = []
        st.session_state["thermography_timeline"] = []
        st.session_state.pop("thermography_timeline_t0", None)
        st.session_state.pop("thermography_timeline_ti", None)
        st.info(
            "A timeline temporária anterior foi limpa para habilitar o ajuste "
            "dinâmico de temperatura. Adicione as coletas novamente."
        )
    entries = sorted(
        (
            entry
            for entry in timeline_entries
            if int(entry["athlete_id"]) == int(selected_player_id)
        ),
        key=_timeline_sort_key,
    )
    valid_ids = {int(entry["id"]) for entry in entries}
    for role in ("t0", "ti"):
        key = f"thermography_timeline_{role}"
        if st.session_state.get(key) not in valid_ids:
            st.session_state.pop(key, None)
    if not entries:
        st.caption(
            "Analise um par de imagens e use “Adicionar à timeline”. "
            "As imagens permanecem somente nesta sessão."
        )
        return

    action_column, clear_column = st.columns([4, 1])
    with action_column:
        role_label = st.radio(
            "Ao clicar em uma coleta, definir como:",
            ("Basal", "Atual"),
            horizontal=True,
            key="thermography_timeline_role_v2",
        )
    with clear_column:
        if st.button("Limpar timeline", use_container_width=True):
            st.session_state["thermography_timeline"] = []
            st.session_state.pop("thermography_timeline_t0", None)
            st.session_state.pop("thermography_timeline_ti", None)
            st.rerun()
    role = "t0" if "Basal" in role_label else "ti"
    selected_t0 = st.session_state.get("thermography_timeline_t0")
    selected_ti = st.session_state.get("thermography_timeline_ti")
    card_styles = []
    for entry in entries:
        entry_id = int(entry["id"])
        active_selection = selected_t0 if role == "t0" else selected_ti
        is_selected = entry_id == active_selection
        selector = f".st-key-timeline_card_{entry_id}"
        border_selector = (
            f'{selector} [data-testid="stVerticalBlockBorderWrapper"]'
        )
        if is_selected:
            card_styles.append(
                f"{selector} {{ opacity: 1; }}"
                f"{border_selector} {{ border: 3px solid "
                "rgba(49, 51, 63, 0.95) !important; }}"
            )
        else:
            card_styles.append(
                f"{selector} {{ opacity: 0.38; transition: opacity 0.18s ease; }}"
                f"{selector}:hover {{ opacity: 0.72; }}"
            )
    if card_styles:
        st.markdown(
            "<style>" + "".join(card_styles) + "</style>",
            unsafe_allow_html=True,
        )
    st.caption(
        f"Mostrando a seleção de {role_label}: somente a coleta escolhida "
        "neste estado permanece destacada."
    )
    with st.container(horizontal=True):
        for entry in entries:
            entry_id = int(entry["id"])
            with st.container(
                border=True,
                width=190,
                key=f"timeline_card_{entry_id}",
            ):
                thumbnail = entry["views"]["front"]["image"].copy()
                thumbnail.thumbnail((170, 110))
                st.image(thumbnail, width="stretch")
                label = entry["collected_at"].strftime("%d/%m/%Y")
                st.button(
                    label,
                    key=f"timeline_entry_{entry_id}_{role}",
                    use_container_width=True,
                    on_click=_select_timeline_entry_by_id,
                    args=(entry_id, role),
                )
                st.caption(f"Coleta #{entry['sequence']}")
    st.caption("As imagens da timeline são temporárias e serão perdidas ao encerrar a sessão.")

    t0 = _timeline_entry_by_id(st.session_state.get("thermography_timeline_t0"))
    ti = _timeline_entry_by_id(st.session_state.get("thermography_timeline_ti"))
    if t0 is not None and ti is not None:
        if _timeline_sort_key(ti) < _timeline_sort_key(t0):
            st.warning(
                "A coleta Atual está registrada antes da Basal. A comparação "
                "continua disponível, mas confira se essa ordem foi intencional."
            )
        _render_comparison(t0, ti)


def add_to_timeline(
    athlete_id: int,
    collected_at: date | None,
    views: dict[str, dict[str, Any]],
    items: dict[str, dict[str, Any]],
) -> None:
    timeline: list[dict[str, Any]] = st.session_state.setdefault(
        "thermography_timeline", []
    )
    sequence = int(st.session_state.get("thermography_timeline_sequence", 0)) + 1
    st.session_state["thermography_timeline_sequence"] = sequence
    stored_views: dict[str, dict[str, Any]] = {}
    for view_key, view in views.items():
        analysis = items[f"{view_key}:{view['signature']}"]["analysis"]
        stored_views[view_key] = {
            "image": view["image"].copy(),
            "minimum_temperature": float(items[f"{view_key}:{view['signature']}"]["minimum_temperature"]),
            "maximum_temperature": float(items[f"{view_key}:{view['signature']}"]["maximum_temperature"]),
            "default_threshold": float(analysis["threshold"]),
            "boxes": {side: dict(box) for side, box in analysis["boxes"].items()},
            "temperatures": analysis["temperatures"].copy(),
            "segmentation_masks": {
                side: analysis["masks"][side].astype(bool).copy()
                for side in LEGS.values()
            },
        }
    entry = {
        "version": 2,
        "id": sequence,
        "sequence": sequence,
        "athlete_id": int(athlete_id),
        "collected_at": collected_at or current_sao_paulo_date(),
        "views": stored_views,
    }
    timeline.append(entry)
    st.session_state["thermography_timeline_ti"] = sequence
    existing_t0 = _timeline_entry_by_id(
        st.session_state.get("thermography_timeline_t0")
    )
    if existing_t0 is None:
        st.session_state["thermography_timeline_t0"] = sequence
    st.session_state["thermography_timeline_message"] = "Coleta adicionada à timeline da sessão."


@st.dialog("Data da coleta")
def confirm_timeline_date(
    athlete_id: int,
    views: dict[str, dict[str, Any]],
    items: dict[str, dict[str, Any]],
    pair_signature: str,
) -> None:
    st.caption("Informe a data em que as imagens termográficas foram coletadas.")
    collected_at = st.date_input(
        "Data de registro da coleta",
        value=current_sao_paulo_date(),
        key=f"timeline_collection_date_{pair_signature}",
    )
    if st.button(
        "Confirmar e adicionar à timeline",
        type="primary",
        use_container_width=True,
        key=f"confirm_timeline_date_{pair_signature}",
    ):
        add_to_timeline(athlete_id, collected_at, views, items)
        st.rerun()

