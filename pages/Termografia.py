from __future__ import annotations

import hashlib
import io
from datetime import date
from typing import Any

import cv2
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image, ImageOps, UnidentifiedImageError
from streamlit_drawable_konva import crop_box_from_json, st_canvas

from athlete_matching import unique_matching_athlete_id
from thermal_analysis import (
    annotate_boxes, compare_hot_masks, count_hot_pixels, detect_colorbar_box, detect_leg_boxes,
    hot_pixels_overlay, segmentation_overlay, segment_leg_mask, temperature_matrix,
    scale_percentage_from_temperature,
    temperature_from_scale_percentage,
)
from thermography_data import (
    athlete_label,
    load_thermography_athletes,
    load_thermography_history,
)
from thermography_service import (
    DuplicateThermographyError,
    LegacyThermographyRecord,
    current_sao_paulo_date,
)
from thermography_timeline import valid_timeline_selection
from service_gateway import (
    extract_thermography_scale,
    extract_legacy_documents,
    save_image_thermography,
    save_legacy_thermography,
)

st.set_page_config(
    page_title="MAC Performance | Termografia", page_icon="🌡️", layout="wide"
)

MAX_IMAGE_SIZE = 20 * 1024 * 1024
DEFAULT_MIN_TEMPERATURE = 20.0
DEFAULT_MAX_TEMPERATURE = 40.0
DEFAULT_HOT_POSITION = 0.90
PERCENTAGE_MODE = "Porcentagem da escala"
TEMPERATURE_MODE = "Temperatura (°C)"
THRESHOLD_MODE_KEY = "thermography_threshold_mode"
LEGS = {"Perna direita": "right", "Perna esquerda": "left"}
VIEW_LABELS = {"front": "Frente", "back": "Verso"}


def threshold_mode_key(view_key: str) -> str:
    return f"{THRESHOLD_MODE_KEY}_{view_key}"


def synchronize_threshold_mode(source_key: str) -> None:
    """Mantém os seletores de frente e verso com a mesma opção."""
    selected_mode = st.session_state[source_key]
    st.session_state[THRESHOLD_MODE_KEY] = selected_mode
    for view_key in VIEW_LABELS:
        target_key = threshold_mode_key(view_key)
        if target_key != source_key:
            st.session_state[target_key] = selected_mode


def load_thermography(content: bytes) -> Image.Image:
    """Valida e normaliza a imagem enviada sem persistir o arquivo."""
    if not content:
        raise ValueError("A imagem enviada está vazia.")
    if len(content) > MAX_IMAGE_SIZE:
        raise ValueError("A imagem deve ter no máximo 20 MB.")
    try:
        with Image.open(io.BytesIO(content)) as source:
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (OSError, UnidentifiedImageError) as error:
        raise ValueError("O arquivo enviado não é uma imagem válida.") from error
    if image.width < 2 or image.height < 2:
        raise ValueError("A imagem não possui dimensões válidas.")
    return image


def image_signature(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _display_image(
    image: Image.Image,
    max_width: int = 850,
    max_height: int | None = None,
) -> tuple[Image.Image, float]:
    limits = [2.0, max_width / image.width]
    if max_height is not None:
        limits.append(max_height / image.height)
    scale = min(limits)
    if scale == 1.0:
        return image, scale
    return image.resize(
        (int(round(image.width * scale)), int(round(image.height * scale))),
        Image.Resampling.NEAREST,
    ), scale


def _scaled_box(
    crop: tuple[int, int, int, int], scale: float, image: Image.Image
) -> dict[str, int]:
    x, y, width, height = crop
    left = max(0, min(image.width - 1, int(round(x / scale))))
    top = max(0, min(image.height - 1, int(round(y / scale))))
    right = max(left + 1, min(image.width, int(round((x + width) / scale))))
    bottom = max(top + 1, min(image.height, int(round((y + height) / scale))))
    return {"left": left, "top": top, "width": right - left, "height": bottom - top}


def _automatic_boxes(image: Image.Image, view_key: str) -> dict[str, dict[str, int]]:
    detected = detect_leg_boxes(image)
    if len(detected) < 2:
        width, height = image.size
        defaults = [
            {"left": int(width * .12), "top": int(height * .28),
             "width": int(width * .62), "height": int(height * .30)},
            {"left": int(width * .12), "top": int(height * .60),
             "width": int(width * .62), "height": int(height * .30)},
        ]
        detected = [*detected, *defaults[len(detected):]]
    first, second = detected[:2]
    return (
        {"right": first, "left": second}
        if view_key == "front" else {"left": first, "right": second}
    )


def _canvas_seeds(
    image_data: np.ndarray, image: Image.Image, box: dict[str, int]
) -> tuple[np.ndarray, int, int]:
    rgba = np.asarray(image_data, dtype=np.uint8)
    rgba = cv2.resize(rgba, image.size, interpolation=cv2.INTER_NEAREST)
    red, green, blue = rgba[:, :, 0], rgba[:, :, 1], rgba[:, :, 2]
    alpha = rgba[:, :, 3] if rgba.shape[2] > 3 else np.full(red.shape, 255, np.uint8)
    foreground = (alpha > 20) & (green > 245) & (red < 35) & (blue < 35)
    background = (alpha > 20) & (red > 245) & (green < 35) & (blue < 35)
    inside = np.zeros(red.shape, dtype=bool)
    left, top = box["left"], box["top"]
    inside[top:top + box["height"], left:left + box["width"]] = True
    foreground &= inside
    background &= inside
    seeds = np.zeros(red.shape, dtype=np.int8)
    seeds[foreground] = 1
    seeds[background] = -1
    return seeds, int(foreground.sum()), int(background.sum())


def _invalidate_segmentation(item: dict[str, Any]) -> None:
    item.pop("analysis", None)
    item.pop("analysis_config", None)


def _highlight_colorbar(
    overlay: Image.Image, original: Image.Image, box: dict[str, int]
) -> Image.Image:
    preview = np.asarray(overlay.convert("RGB"), dtype=np.uint8).copy()
    source = np.asarray(original.convert("RGB"), dtype=np.uint8)
    left, top = box["left"], box["top"]
    right = min(original.width, left + box["width"])
    bottom = min(original.height, top + box["height"])
    preview[top:bottom, left:right] = source[top:bottom, left:right]
    return annotate_boxes(Image.fromarray(preview), {"Barra térmica": box})


@st.dialog("Corrigir áreas", width="large")
def edit_thermal_boxes(
    item_key: str,
    image: Image.Image,
    automatic: dict[str, dict[str, int]],
    automatic_colorbar: dict[str, int],
) -> None:
    item = st.session_state["thermography_items"][item_key]
    if message := st.session_state.pop(f"thermal_box_message_{item_key}", None):
        st.success(message)
    target_label = st.radio(
        "Área", ("Perna direita", "Perna esquerda", "Barra de cores"),
        horizontal=True,
        key=f"thermal_box_target_{item_key}",
    )
    is_colorbar = target_label == "Barra de cores"
    side = "right" if target_label == "Perna direita" else "left"
    boxes = {**automatic, **item.get("manual_boxes", {})}
    colorbar = item.get("manual_colorbar_box", automatic_colorbar)
    preview = annotate_boxes(image, {
        "Perna direita": boxes["right"], "Perna esquerda": boxes["left"],
        "Barra térmica": colorbar,
    })
    background, scale = _display_image(preview, max_width=620, max_height=360)
    st.caption(
        "Desenhe um retângulo somente sobre a faixa colorida vertical."
        if is_colorbar else
        "Desenhe um retângulo sobre toda a área da perna selecionada."
    )
    canvas = st_canvas(
        fill_color="rgba(0,255,255,0.12)", stroke_color="#00FFFF",
        stroke_width=3, background_image=background,
        height=background.height, width=background.width,
        drawing_mode="rect_crop", display_toolbar=True,
        enable_viewport_controls=True,
        key=f"thermal_box_canvas_{item_key}_{'colorbar' if is_colorbar else side}",
    )
    crop = crop_box_from_json(canvas.json_data)
    apply_column, reset_column, finish_column = st.columns([2, 2, 1])
    if apply_column.button("Aplicar área", type="primary", disabled=crop is None):
        selected_box = _scaled_box(crop, scale, image)
        if is_colorbar:
            item["manual_colorbar_box"] = selected_box
        else:
            item.setdefault("manual_boxes", {})[side] = selected_box
            item.setdefault("mask_seeds", {}).pop(side, None)
        _invalidate_segmentation(item)
        st.session_state[f"thermal_box_message_{item_key}"] = (
            f"Área de {target_label.lower()} atualizada."
        )
        st.rerun(scope="fragment")
    if reset_column.button("Restaurar detecção automática"):
        if is_colorbar:
            item.pop("manual_colorbar_box", None)
        else:
            item.setdefault("manual_boxes", {}).pop(side, None)
            item.setdefault("mask_seeds", {}).pop(side, None)
        _invalidate_segmentation(item)
        st.session_state[f"thermal_box_message_{item_key}"] = (
            f"Área de {target_label.lower()} restaurada."
        )
        st.rerun(scope="fragment")
    if finish_column.button("Concluir"):
        st.rerun()


@st.dialog("Corrigir segmentação", width="large")
def edit_thermal_mask(
    item_key: str, image: Image.Image, analysis: dict[str, Any]
) -> None:
    item = st.session_state["thermography_items"][item_key]
    analysis = item.get("analysis", analysis)
    if message := st.session_state.pop(f"thermal_mask_message_{item_key}", None):
        st.success(message)
    target_label = st.radio(
        "Perna", ("Perna direita", "Perna esquerda"), horizontal=True,
        key=f"thermal_mask_target_{item_key}",
    )
    side = "right" if target_label == "Perna direita" else "left"
    brush_label = st.radio(
        "Pincel", ("Incluir área", "Excluir área"), horizontal=True,
        key=f"thermal_brush_{item_key}",
    )
    brush_size = st.slider(
        "Tamanho do pincel", 2, 40, 10, key=f"thermal_brush_size_{item_key}"
    )
    st.caption("Verde inclui pixels na área; vermelho exclui pixels da área.")
    background, _ = _display_image(
        analysis["overlay"], max_width=620, max_height=360
    )
    canvas = st_canvas(
        fill_color="rgba(0,0,0,0)",
        stroke_color="#00FF00" if brush_label == "Incluir área" else "#FF0000",
        stroke_width=brush_size, background_image=background,
        height=background.height, width=background.width,
        drawing_mode="freedraw", display_toolbar=True,
        enable_viewport_controls=True,
        key=f"thermal_mask_canvas_{item_key}_{side}",
    )
    def recalculate(selected_side: str) -> None:
        selected_mask = segment_leg_mask(
            image,
            analysis["boxes"][selected_side],
            item.get("mask_seeds", {}).get(selected_side),
        )
        analysis["masks"][selected_side] = selected_mask
        hot_pixels, total_pixels = count_hot_pixels(
            analysis["temperatures"],
            analysis["boxes"][selected_side],
            analysis["threshold"],
            selected_mask,
        )
        analysis["metrics"][selected_side] = {
            "hot_pixels": hot_pixels,
            "total_pixels": total_pixels,
            "hot_percentage": hot_pixels / total_pixels * 100,
            "threshold": analysis["threshold"],
        }
        analysis["overlay"] = segmentation_overlay(
            image, analysis["boxes"], analysis["masks"]
        )
        analysis["overlay"] = _highlight_colorbar(
            analysis["overlay"], image, analysis["colorbar_box"]
        )
        analysis["hot_overlay"] = hot_pixels_overlay(
            image, analysis["temperatures"], analysis["masks"],
            analysis["threshold"],
        )
        item["analysis"] = analysis

    apply_column, reset_column, finish_column = st.columns([2, 2, 1])
    if apply_column.button("Aplicar traços e recalcular", type="primary"):
        if canvas.image_data is None:
            st.warning("Faça ao menos um traço antes de aplicar.")
            return
        seeds, included, excluded = _canvas_seeds(
            canvas.image_data, image, analysis["boxes"][side]
        )
        if included + excluded == 0:
            st.warning("Nenhum traço verde ou vermelho foi identificado.")
            return
        previous = item.setdefault("mask_seeds", {}).get(side)
        if previous is not None:
            seeds[(seeds == 0) & (previous != 0)] = previous[(seeds == 0) & (previous != 0)]
        item["mask_seeds"][side] = seeds
        recalculate(side)
        item.pop("analysis_config", None)
        st.session_state[f"thermal_mask_message_{item_key}"] = (
            f"Segmentação de {target_label.lower()} recalculada. "
            "Você pode continuar corrigindo."
        )
        st.rerun(scope="fragment")
    if reset_column.button("Restaurar máscara automática"):
        item.setdefault("mask_seeds", {}).pop(side, None)
        recalculate(side)
        item.pop("analysis_config", None)
        st.session_state[f"thermal_mask_message_{item_key}"] = (
            f"Máscara automática de {target_label.lower()} restaurada."
        )
        st.rerun(scope="fragment")
    if finish_column.button("Concluir"):
        st.rerun()


@st.cache_data(show_spinner=False)
def cached_temperature_scale(content: bytes) -> dict[str, float]:
    return extract_thermography_scale(content)


def segmented_analysis(
    image: Image.Image,
    view_key: str,
    minimum_temperature: float,
    maximum_temperature: float,
    threshold: float,
    item: dict[str, Any],
) -> dict[str, Any]:
    automatic = _automatic_boxes(image, view_key)
    boxes = {**automatic, **item.get("manual_boxes", {})}
    automatic_colorbar, colorbar_confidence = detect_colorbar_box(image)
    colorbar = item.get("manual_colorbar_box", automatic_colorbar)
    seeds = item.get("mask_seeds", {})
    config = (
        minimum_temperature, maximum_temperature, threshold,
        tuple(colorbar.items()),
        tuple((side, tuple(boxes[side].items())) for side in ("right", "left")),
        tuple(
            (side, hashlib.sha256(seed.tobytes()).hexdigest())
            for side, seed in sorted(seeds.items())
        ),
    )
    if item.get("analysis_config") == config and item.get("analysis") is not None:
        return item["analysis"]

    temperatures = temperature_matrix(
        image, minimum_temperature, maximum_temperature, colorbar
    )
    masks = {
        side: segment_leg_mask(image, box, seeds.get(side))
        for side, box in boxes.items()
    }
    metrics: dict[str, dict[str, float | int]] = {}
    for side, box in boxes.items():
        hot_pixels, total_pixels = count_hot_pixels(
            temperatures, box, threshold, masks[side]
        )
        metrics[side] = {
            "hot_pixels": hot_pixels,
            "total_pixels": total_pixels,
            "hot_percentage": hot_pixels / total_pixels * 100,
            "threshold": threshold,
        }
    overlay = segmentation_overlay(image, boxes, masks)
    overlay = _highlight_colorbar(overlay, image, colorbar)
    analysis = {
        "view": view_key, "boxes": boxes, "masks": masks,
        "metrics": metrics,
        "overlay": overlay,
        "hot_overlay": hot_pixels_overlay(
            image, temperatures, masks, threshold
        ),
        "automatic_boxes": automatic,
        "colorbar_box": colorbar,
        "automatic_colorbar_box": automatic_colorbar,
        "colorbar_confidence": colorbar_confidence,
        "temperatures": temperatures,
        "threshold": threshold,
    }
    item["analysis_config"] = config
    item["analysis"] = analysis
    return analysis


def render_view(
    view_key: str,
    name: str,
    content: bytes,
    image: Image.Image,
    item: dict[str, Any],
    item_key: str,
) -> dict[str, dict[str, float | int]] | None:
    """Renderiza uma vista e retorna as métricas das duas pernas."""
    view_label = VIEW_LABELS[view_key]
    st.markdown(f"#### Imagem de {view_label.lower()}")
    st.caption(name)
    if item.get("scale_detected"):
        st.caption("Tmin e Tmax reconhecidos automaticamente na imagem.")
    else:
        st.info(
            "A escala não foi reconhecida automaticamente. Confira os valores "
            "iniciais e ajuste-os manualmente, se necessário."
        )

    with st.container(border=True):
        mode_key = threshold_mode_key(view_key)
        threshold_mode = st.radio(
            "Escala do limiar de pixels quentes:",
            options=(PERCENTAGE_MODE, TEMPERATURE_MODE),
            horizontal=True,
            key=mode_key,
            on_change=synchronize_threshold_mode,
            args=(mode_key,),
        )
        minimum_column, maximum_column = st.columns(2)
        with minimum_column:
            minimum_temperature = st.number_input(
                "Temperatura mínima — Tmin (°C)",
                value=float(item["minimum_temperature"]),
                step=0.1,
                format="%.1f",
                key=f"thermography_tmin_{view_key}_{image_signature(content)}",
            )
        with maximum_column:
            maximum_temperature = st.number_input(
                "Temperatura máxima — Tmax (°C)",
                value=float(item["maximum_temperature"]),
                step=0.1,
                format="%.1f",
                key=f"thermography_tmax_{view_key}_{image_signature(content)}",
            )

        item["minimum_temperature"] = minimum_temperature
        item["maximum_temperature"] = maximum_temperature
        valid_scale = maximum_temperature > minimum_temperature
        if valid_scale:
            signature = image_signature(content)
            percentage_key = f"thermography_threshold_percentage_{view_key}_{signature}"
            temperature_key = f"thermography_threshold_temperature_{view_key}_{signature}"
            previous_mode = item.get("threshold_mode")
            stored_percentage = float(
                item.get("threshold_percentage", DEFAULT_HOT_POSITION * 100)
            )
            stored_temperature = float(item.get(
                "threshold_temperature",
                temperature_from_scale_percentage(
                    minimum_temperature, maximum_temperature, stored_percentage
                ),
            ))

            if threshold_mode == PERCENTAGE_MODE:
                if previous_mode == TEMPERATURE_MODE:
                    converted_temperature = min(
                        maximum_temperature,
                        max(minimum_temperature, stored_temperature),
                    )
                    stored_percentage = scale_percentage_from_temperature(
                        minimum_temperature,
                        maximum_temperature,
                        converted_temperature,
                    )
                    st.session_state[percentage_key] = stored_percentage
                percentage = st.slider(
                    "Posição mínima na escala para considerar um pixel quente",
                    min_value=0.0,
                    max_value=100.0,
                    value=stored_percentage,
                    step=1.0,
                    format="%d%%",
                    key=percentage_key,
                )
                threshold = temperature_from_scale_percentage(
                    minimum_temperature, maximum_temperature, percentage
                )
                item["threshold_percentage"] = percentage
                item["threshold_temperature"] = threshold
                st.caption("Valor padrão: 90% da escala térmica informada.")
            else:
                if previous_mode == PERCENTAGE_MODE:
                    stored_temperature = temperature_from_scale_percentage(
                        minimum_temperature, maximum_temperature, stored_percentage
                    )
                    st.session_state[temperature_key] = stored_temperature
                slider_step = max(
                    (maximum_temperature - minimum_temperature) / 200, 0.01
                )
                widget_temperature = float(
                    st.session_state.get(temperature_key, stored_temperature)
                )
                clamped_temperature = min(
                    maximum_temperature,
                    max(minimum_temperature, widget_temperature),
                )
                if widget_temperature != clamped_temperature:
                    st.session_state[temperature_key] = clamped_temperature
                threshold = st.slider(
                    "Temperatura mínima para considerar um pixel quente (°C)",
                    min_value=float(minimum_temperature),
                    max_value=float(maximum_temperature),
                    value=float(clamped_temperature),
                    step=float(slider_step),
                    key=temperature_key,
                )
                item["threshold_temperature"] = threshold
                item["threshold_percentage"] = scale_percentage_from_temperature(
                    minimum_temperature, maximum_temperature, threshold
                )
            item["threshold_mode"] = threshold_mode
        else:
            threshold = minimum_temperature
            st.error("Tmax deve ser maior que Tmin.")

    if not valid_scale:
        return None
    try:
        with st.spinner(f"Analisando a imagem de {view_label.lower()}..."):
            analysis = segmented_analysis(
                image, view_key, minimum_temperature, maximum_temperature,
                threshold, item,
            )
    except ValueError as error:
        st.image(image, caption=f"Imagem de {view_label.lower()}", width="stretch")
        st.error(str(error))
        st.info("Corrija as áreas das pernas e tente processar novamente.")
        return None

    boxes = analysis["boxes"]
    if view_key == "front":
        convention = "Frente: R1 superior = direita; R2 inferior = esquerda."
    else:
        convention = "Verso: R1 superior = esquerda; R2 inferior = direita."

    st.markdown("##### Segmentação das pernas")
    segmentation_column, temperature_column = st.columns(2, gap="medium")
    with segmentation_column:
        st.image(
            analysis["overlay"],
            caption=f"Área segmentada — {convention}",
            width="stretch",
        )
    with temperature_column:
        st.image(
            analysis["hot_overlay"],
            caption=f"Pixels quentes detectados — temperatura ≥ {threshold:.1f} °C",
            width="stretch",
        )
    st.caption(convention)
    st.caption(
        "Barra térmica detectada automaticamente · confiança heurística: "
        f"{analysis['colorbar_confidence']:.0%}."
    )
    edit_columns = st.columns(2)
    if edit_columns[0].button(
        "Corrigir áreas", key=f"thermal_edit_boxes_{item_key}",
        width="stretch",
    ):
        edit_thermal_boxes(
            item_key, image, analysis["automatic_boxes"],
            analysis["automatic_colorbar_box"],
        )
    if edit_columns[1].button(
        "Corrigir segmentação", key=f"thermal_edit_masks_{item_key}",
        width="stretch",
    ):
        edit_thermal_mask(item_key, image, analysis)
    metrics = analysis["metrics"]

    st.markdown("##### Métricas da área segmentada")
    metric_columns = st.columns(2)
    for column, (label, key) in zip(metric_columns, LEGS.items()):
        metric = metrics[key]
        with column:
            with st.container(border=True):
                st.metric(
                    f"Pixels quentes — {label}",
                    f"{metric['hot_pixels']:,} px".replace(",", "."),
                    help="Quantidade de pixels quentes dentro da máscara da perna.",
                )
                metric_caption = (
                    f"Área da perna: {metric['total_pixels']:,} pixels · "
                    f"Pixels quentes: {metric['hot_percentage']:.1f}% · "
                    f"temperatura ≥ {threshold:.1f} °C"
                )
                st.caption(metric_caption.replace(",", "."))
    return metrics


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
    other_role = "ti" if role == "t0" else "t0"
    other = _timeline_entry_by_id(
        st.session_state.get(f"thermography_timeline_{other_role}")
    )
    if other is not None:
        selected_key = _timeline_sort_key(entry)
        other_key = _timeline_sort_key(other)
        if not valid_timeline_selection(selected_key, other_key, role):
            st.session_state["thermography_timeline_message"] = (
                "T0 deve ser anterior ou igual a Ti. Escolha outra coleta."
            )
            return
    st.session_state[f"thermography_timeline_{role}"] = int(entry["id"])


def _render_comparison(t0: dict[str, Any], ti: dict[str, Any]) -> None:
    st.markdown("#### Comparação T0 × Ti")
    st.caption(
        f"Basal: {t0['collected_at'].strftime('%d/%m/%Y')} · "
        f"Atual: {ti['collected_at'].strftime('%d/%m/%Y')}"
    )
    tabs = st.tabs(["Frente", "Verso"])
    for tab, view_key in zip(tabs, ("front", "back")):
        with tab:
            baseline = t0["views"][view_key]
            current = ti["views"][view_key]
            t0_column, ti_column, map_column, metrics_column = st.columns(
                [1.1, 1.1, 1.4, 1.2], gap="medium"
            )
            with t0_column:
                st.markdown("##### T0 — Basal")
                st.image(baseline["image"], width="stretch")
            with ti_column:
                st.markdown("##### Ti — Atual")
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
                st.caption("🔴 novos · 🟡 persistentes · 🔵 resolvidos")
            with metrics_column:
                st.markdown("##### Métricas de Ti")
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

    entries = sorted(
        (
            entry
            for entry in st.session_state.get("thermography_timeline", [])
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
            ("T0 — Basal", "Ti — Atual"),
            horizontal=True,
            key="thermography_timeline_role",
        )
    with clear_column:
        if st.button("Limpar timeline", use_container_width=True):
            st.session_state["thermography_timeline"] = []
            st.session_state.pop("thermography_timeline_t0", None)
            st.session_state.pop("thermography_timeline_ti", None)
            st.rerun()
    role = "t0" if role_label.startswith("T0") else "ti"
    selected_t0 = st.session_state.get("thermography_timeline_t0")
    selected_ti = st.session_state.get("thermography_timeline_ti")
    with st.container(horizontal=True):
        for entry in entries:
            entry_id = int(entry["id"])
            states = []
            if entry_id == selected_t0:
                states.append("T0")
            if entry_id == selected_ti:
                states.append("Ti")
            with st.container(border=True, width=190):
                thumbnail = entry["views"]["front"]["image"].copy()
                thumbnail.thumbnail((170, 110))
                st.image(thumbnail, width="stretch")
                label = entry["collected_at"].strftime("%d/%m/%Y")
                if states:
                    label += " · " + "/".join(states)
                if st.button(
                    label,
                    key=f"timeline_entry_{entry_id}_{role}",
                    use_container_width=True,
                ):
                    _select_timeline_entry(entry, role)
                    st.rerun()
                st.caption(f"Coleta #{entry['sequence']}")
    st.caption("As imagens da timeline são temporárias e serão perdidas ao encerrar a sessão.")

    t0 = _timeline_entry_by_id(st.session_state.get("thermography_timeline_t0"))
    ti = _timeline_entry_by_id(st.session_state.get("thermography_timeline_ti"))
    if t0 is not None and ti is not None:
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
            "threshold": float(analysis["threshold"]),
            "boxes": {side: dict(box) for side, box in analysis["boxes"].items()},
            "metrics": {
                side: dict(metric) for side, metric in analysis["metrics"].items()
            },
            "hot_masks": {
                side: (
                    analysis["masks"][side].astype(bool)
                    & np.isfinite(analysis["temperatures"])
                    & (analysis["temperatures"] >= analysis["threshold"])
                ).copy()
                for side in LEGS.values()
            },
        }
    entry = {
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
    if existing_t0 is None or _timeline_sort_key(existing_t0) > _timeline_sort_key(entry):
        st.session_state["thermography_timeline_t0"] = sequence
    st.session_state["thermography_timeline_message"] = "Coleta adicionada à timeline da sessão."


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

def render_forms() -> None:
    """Renderiza o fluxo opcional de importação de formulários manuscritos."""
    with st.expander("Formulários", expanded=False):
        legacy_documents = st.file_uploader(
            "Planilhas e fichas preenchidas manualmente",
            type=["pdf", "png", "jpg", "jpeg"],
            accept_multiple_files=True,
            help=(
                "Os documentos são enviados ao LlamaParse Cloud para extração. "
                "Se o serviço falhar ou a tabela não for reconhecida, o sistema "
                "usa o OCR local como alternativa."
            ),
            key="thermography_legacy_documents",
        )

        if legacy_documents:
            batch_signature = hashlib.sha256(
                b"".join(
                    hashlib.sha256(document.getvalue()).digest()
                    for document in legacy_documents
                )
            ).hexdigest()
            if st.session_state.get("legacy_batch_signature") != batch_signature:
                st.session_state.pop("legacy_extraction_results", None)
                st.session_state.pop("legacy_edited_rows", None)

            if st.button(
                "Extrair conteúdo",
                type="primary",
                key="extract_legacy_documents",
            ):
                extracted_documents = []
                progress = st.progress(0, text="Preparando documentos...")
                for index, document in enumerate(legacy_documents):
                    try:
                        _, extraction = extract_legacy_documents(
                            [(document.name, document.getvalue())]
                        )[0]
                        extracted_documents.append(
                            {
                                "filename": document.name,
                                "pages": extraction.pages,
                                "used_fallback": extraction.used_fallback,
                                "fallback_reason": extraction.fallback_reason,
                                "error": None,
                            }
                        )
                    except Exception as error:
                        extracted_documents.append(
                            {
                                "filename": document.name,
                                "pages": [],
                                "error": str(error),
                            }
                        )
                    progress.progress(
                        (index + 1) / len(legacy_documents),
                        text=f"Processando {document.name}",
                    )
                progress.empty()
                st.session_state["legacy_batch_signature"] = batch_signature
                st.session_state["legacy_extraction_results"] = extracted_documents
        else:
            st.session_state.pop("legacy_batch_signature", None)
            st.session_state.pop("legacy_extraction_results", None)
            st.session_state.pop("legacy_edited_rows", None)
            st.caption(
                "Envie os documentos e execute a extração. "
                "Nenhum arquivo é persistido pelo protótipo."
            )

        extraction_results = st.session_state.get("legacy_extraction_results", [])
        if extraction_results:
            extracted_rows = []
            for document_result in extraction_results:
                with st.expander(document_result["filename"]):
                    if document_result["error"]:
                        st.error(document_result["error"])
                        continue
                    if document_result.get("used_fallback"):
                        st.warning(
                            "LlamaParse não pôde concluir a extração; foi utilizado "
                            "o OCR local (Tesseract). "
                            + str(document_result.get("fallback_reason") or "")
                        )
                    for page_number, page_result in enumerate(
                        document_result["pages"], start=1
                    ):
                        st.markdown(f"**Página {page_number}**")
                        diagnostic = page_result["diagnostic"].copy()
                        diagnostic.thumbnail((900, 700))
                        st.image(
                            diagnostic,
                            caption=(
                                "Linhas candidatas identificadas em verde"
                                if document_result.get("used_fallback")
                                else "Página enviada para extração"
                            ),
                            width=700,
                        )
                        if page_result.get("error"):
                            st.error(page_result["error"])
                            continue
                        if page_result["date"]:
                            st.caption(f"Data identificada: {page_result['date']}")
                        else:
                            st.warning("A data da página não foi identificada.")
                        for row in page_result["rows"]:
                            review_row = {
                                key: value
                                for key, value in row.items()
                                if key not in {
                                    "_raw",
                                    "Confiança OCR",
                                    "Revisão",
                                }
                            }
                            recognized_name = review_row.get("Jogador", "")
                            matched_athlete_id = unique_matching_athlete_id(
                                recognized_name, athletes
                            )
                            review_row["Nome reconhecido"] = recognized_name
                            review_row["Jogador"] = (
                                editor_label_by_athlete_id.get(matched_athlete_id)
                                if matched_athlete_id is not None else None
                            )
                            extracted_rows.append(review_row)
                        if not page_result["rows"]:
                            st.warning("Nenhuma linha preenchida foi identificada.")

            if extracted_rows:
                st.markdown("#### Revisão da extração")
                st.caption(
                    "Confira os valores e selecione um jogador cadastrado em todas "
                    "as linhas antes de registrar no banco."
                )
                review_columns = [
                    "Nome reconhecido",
                    "Jogador",
                    "Massa",
                    "EVA Dor",
                    "Frente",
                    "Verso",
                    "Observações",
                    "Data",
                ]
                review_frame = pd.DataFrame(extracted_rows).reindex(columns=review_columns)
                review_frame["Nome reconhecido"] = review_frame[
                    "Nome reconhecido"
                ].astype("string")
                review_frame["Jogador"] = review_frame["Jogador"].astype("string")
                review_frame["Massa"] = pd.to_numeric(
                    review_frame["Massa"], errors="coerce"
                ).astype("Float64")
                for numeric_column in ("EVA Dor", "Frente", "Verso"):
                    review_frame[numeric_column] = pd.to_numeric(
                        review_frame[numeric_column], errors="coerce"
                    ).astype("Int64")
                review_frame["Observações"] = (
                    review_frame["Observações"].fillna("").astype("string")
                )
                review_frame["Data"] = pd.to_datetime(
                    review_frame["Data"], errors="coerce"
                )
                editor_batch_key = st.session_state.get(
                    "legacy_batch_signature", "sem_lote"
                )
                edited_rows = st.data_editor(
                    review_frame,
                    width="stretch",
                    hide_index=True,
                    num_rows="dynamic",
                    disabled=["Nome reconhecido"],
                    column_order=review_columns,
                    column_config={
                        "Nome reconhecido": st.column_config.TextColumn(),
                        "Jogador": st.column_config.SelectboxColumn(
                            options=sorted(athlete_id_by_editor_label),
                            required=True,
                        ),
                        "Massa": st.column_config.NumberColumn(
                            min_value=0.1, format="%.1f"
                        ),
                        "EVA Dor": st.column_config.NumberColumn(
                            min_value=0, max_value=10, step=1, format="%d"
                        ),
                        "Frente": st.column_config.NumberColumn(
                            min_value=0, step=1, format="%d"
                        ),
                        "Verso": st.column_config.NumberColumn(
                            min_value=0, step=1, format="%d"
                        ),
                        "Observações": st.column_config.TextColumn(
                            width="large",
                            default="",
                        ),
                        "Data": st.column_config.DateColumn(
                            format="DD/MM/YYYY",
                            required=True,
                        ),
                    },
                    key=f"legacy_review_editor_{editor_batch_key}",
                )
                edited_records = (
                    edited_rows.astype(object)
                    .where(pd.notna(edited_rows), None)
                    .to_dict("records")
                )
                st.session_state["legacy_edited_rows"] = edited_records
                selected_athlete_ids = [
                    athlete_id_by_editor_label.get(row.get("Jogador"))
                    for row in edited_records
                ]
                has_unselected_athletes = any(
                    athlete_id is None for athlete_id in selected_athlete_ids
                )
                if has_unselected_athletes:
                    st.warning(
                        "Selecione um jogador cadastrado para todas as linhas."
                    )
                else:
                    st.success("Todos os jogadores estão vinculados a cadastros.")

                st.info(
                    "Frente e Verso dos documentos serão associados às medidas "
                    "SOMA_FRENTE e SOMA_VERSO. As quatro medidas individuais por "
                    "perna permanecerão vazias nos registros legados."
                )
                if st.button(
                    "Registrar documentos revisados no banco",
                    type="primary",
                    key="save_legacy_thermography",
                    disabled=has_unselected_athletes or not athletes,
                ):
                    try:
                        legacy_records = []
                        for row_number, (row, athlete_id) in enumerate(
                            zip(edited_records, selected_athlete_ids), start=1
                        ):
                            if athlete_id is None:
                                raise ValueError(
                                    f"Linha {row_number}: selecione um jogador."
                                )
                            raw_date = row.get("Data")
                            if raw_date is None or pd.isna(raw_date):
                                raise ValueError(
                                    f"Linha {row_number}: informe a data da coleta."
                                )
                            parsed_date = pd.to_datetime(raw_date, errors="raise").date()
                            raw_observations = row.get("Observações")
                            observations_value = (
                                None
                                if raw_observations is None or pd.isna(raw_observations)
                                else str(raw_observations)
                            )
                            legacy_records.append(
                                LegacyThermographyRecord(
                                    athlete_id=athlete_id,
                                    collected_at=parsed_date,
                                    mass=row.get("Massa"),
                                    pain_score=row.get("EVA Dor"),
                                    front=row.get("Frente"),
                                    back=row.get("Verso"),
                                    observations=observations_value,
                                )
                            )
                        inserted = save_legacy_thermography(legacy_records)
                    except (ValueError, RuntimeError, DuplicateThermographyError) as error:
                        st.error(str(error))
                    except Exception:
                        st.error("Não foi possível registrar os documentos no banco.")
                    else:
                        load_thermography_history.clear()
                        st.session_state["thermography_flash"] = (
                            f"{len(legacy_records)} coleta(s) legada(s) registrada(s) "
                            f"com {inserted} medida(s)."
                        )
                        st.rerun()


st.subheader("Nova análise térmica")
st.caption(
    "Informe os dados da coleta e envie em conjunto as imagens de frente e verso."
)

with st.container(border=True):
    record_columns = st.columns(4)
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
        collection_date = st.date_input(
            "Data da coleta",
            value=current_sao_paulo_date(),
            help="Se nenhuma data for enviada pela API, será usada a data atual de São Paulo.",
            key="thermography_collection_date",
        )
    with record_columns[3]:
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
    render_forms()
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
    render_forms()
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
    front_pixels = sum(
        int(view_metrics["front"][key]["hot_pixels"]) for key in LEGS.values()
    )
    back_pixels = sum(
        int(view_metrics["back"][key]["hot_pixels"]) for key in LEGS.values()
    )
    front_area = sum(
        int(view_metrics["front"][key]["total_pixels"]) for key in LEGS.values()
    )
    back_area = sum(
        int(view_metrics["back"][key]["total_pixels"]) for key in LEGS.values()
    )
    front_percentage = front_pixels / front_area * 100
    back_percentage = back_pixels / back_area * 100
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
        add_to_timeline(
            int(selected_player_id), collection_date, views, items
        )
        st.rerun()

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
        try:
            inserted = save_image_thermography(
                athlete_id=int(prepared_player_id),
                collected_at=collection_date,
                mass=prepared_mass,
                pain_score=prepared_pain_score,
                front_right=view_metrics["front"]["right"]["hot_pixels"],
                front_left=view_metrics["front"]["left"]["hot_pixels"],
                back_right=view_metrics["back"]["right"]["hot_pixels"],
                back_left=view_metrics["back"]["left"]["hot_pixels"],
                observations=prepared_observations,
            )
        except (ValueError, RuntimeError, DuplicateThermographyError) as error:
            st.error(str(error))
        except Exception:
            st.error("Não foi possível registrar a coleta no banco.")
        else:
            load_thermography_history.clear()
            st.session_state["thermography_flash"] = (
                f"Coleta registrada com {inserted} medida(s)."
            )
            st.rerun()
    st.caption("As imagens não são armazenadas; somente as medidas são enviadas.")
else:
    stored_metrics.clear()

st.divider()
render_forms()
