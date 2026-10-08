from __future__ import annotations

import hashlib
import io
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
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
    rgba = np.asarray(Image.fromarray(rgba).resize(image.size, Image.Resampling.NEAREST))
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


def _parts_preview(image: Image.Image, analysis: dict[str, Any],
                   settings: dict[str, dict[str, Any]]) -> Image.Image:
    preview = analysis["overlay"].copy()
    draw = ImageDraw.Draw(preview)
    colors = ("#00e5ff", "#ffff00", "#ff9f1c")
    for side, setting in settings.items():
        _, boundaries = leg_part_metrics(
            analysis["temperatures"], analysis["masks"][side],
            analysis["threshold"], tuple(setting["cuts"]),
            axis=setting["axis"], foot_at_end=setting["foot_at_end"],
        )
        box = analysis["boxes"][side]
        occupied = np.flatnonzero(np.any(
            analysis["masks"][side], axis=0 if setting["axis"] == "horizontal" else 1
        ))
        near, far = int(occupied[0]), int(occupied[-1]) + 1
        endpoints = ((near, *boundaries, far) if setting["foot_at_end"]
                     else (far, *boundaries, near))
        for coordinate, color in zip(boundaries, colors):
            if setting["axis"] == "horizontal":
                line = (coordinate, box["top"], coordinate,
                        box["top"] + box["height"])
            else:
                line = (box["left"], coordinate,
                        box["left"] + box["width"], coordinate)
            draw.line(line, fill=color, width=max(2, image.width // 300))
        try:
            font = ImageFont.truetype('DejaVuSans.ttf', max(12, min(24, image.height // 35)))
        except OSError:
            font = ImageFont.load_default()
        for label, (first, last) in zip(('Coxa', 'Joelho', 'Canela', 'Pé'), zip(endpoints, endpoints[1:])):
            middle = (first + last) // 2
            if setting["axis"] == "horizontal":
                label_position = (middle, box["top"] + box["height"] // 2)
            else:
                label_position = (box["left"] + box["width"] // 2, middle)
            draw.text(label_position, label, font=font, fill="white", anchor="mm",
                      stroke_width=2, stroke_fill="black")
    return preview


@st.dialog("Corrigir Áreas", width="large")
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
        "Desenhe um retângulo somente sobre a faixa colorida da escala."
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
    if apply_column.button("Aplicar área", type="primary", disabled=crop is None, width='stretch'):
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
    if reset_column.button("Restaurar detecção automática", width='stretch'):
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
    if finish_column.button("Concluir", width='stretch'):
        st.rerun()


@st.dialog("Corrigir segmentação", width="large")
def edit_thermal_mask(
    item_key: str, image: Image.Image, analysis: dict[str, Any]
) -> None:
    item = st.session_state["thermography_items"][item_key]
    analysis = item.get("analysis", analysis)
    if message := st.session_state.pop(f"thermal_mask_message_{item_key}", None):
        st.success(message)
    controls = st.columns(3)
    target_label = controls[0].radio(
        "Perna", ("Perna direita", "Perna esquerda"), horizontal=True,
        key=f"thermal_mask_target_{item_key}",
    )
    side = "right" if target_label == "Perna direita" else "left"
    brush_label = controls[1].radio(
        "Pincel", ("Incluir área", "Excluir área"), horizontal=True,
        key=f"thermal_brush_{item_key}",
    )
    brush_size = controls[2].slider(
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
        nonlocal analysis
        _invalidate_segmentation(item)
        analysis = segmented_analysis(image, analysis['view'], item['minimum_temperature'],
                                      item['maximum_temperature'], analysis['threshold'], item)

    apply_column, reset_column, finish_column = st.columns([2, 2, 1])
    if apply_column.button("Aplicar traços e recalcular", type="primary", width='stretch'):
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
    if reset_column.button("Restaurar máscara automática", width='stretch'):
        item.setdefault("mask_seeds", {}).pop(side, None)
        recalculate(side)
        item.pop("analysis_config", None)
        st.session_state[f"thermal_mask_message_{item_key}"] = (
            f"Máscara automática de {target_label.lower()} restaurada."
        )
        st.rerun(scope="fragment")
    if finish_column.button("Concluir", width='stretch'):
        st.rerun()


@st.cache_data(show_spinner=False)
def cached_temperature_scale(content: bytes) -> dict[str, float]:
    return extract_thermography_scale(content)


def segmented_analysis(image, view_key, minimum_temperature, maximum_temperature, threshold, item):
    from frontend.streamlit.api_client.thermal_client import segmented_image
    config = (minimum_temperature, maximum_temperature, threshold, item.get('image_rotation', 0),
              repr(item.get('manual_boxes')), repr(item.get('manual_colorbar_box')),
              tuple((side, hashlib.sha256(seed.tobytes()).hexdigest())
                    for side, seed in sorted(item.get('mask_seeds', {}).items())))
    if item.get('analysis_config') == config and item.get('analysis') is not None:
        return item['analysis']
    analysis = segmented_image(image, view_key, minimum_temperature, maximum_temperature,
                               threshold, item.get('manual_boxes'), item.get('manual_colorbar_box'),
                               item.get('mask_seeds'), image_rotation=item.get('image_rotation', 0))
    item['analysis_config'] = config
    item['analysis'] = analysis
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

    settings = item.setdefault("part_settings_v4", {
        side: {"cuts": list(DEFAULT_PART_CUTS), "axis": "horizontal",
               "foot_at_end": False}
        for side in ("right", "left")
    })
    st.markdown("##### Divisão anatômica")
    st.caption(
        "Escolha onde começa a coxa. Os percentuais vão da coxa ao pé, "
        "mesmo quando a imagem está invertida. Cada parte usa apenas "
        "os pixels da máscara."
    )
    part_columns = st.columns(2)
    invalid_cuts = False
    for column, (label, side) in zip(part_columns, LEGS.items()):
        setting = settings.setdefault(
            side, {"cuts": list(DEFAULT_PART_CUTS), "axis": "horizontal",
                   "foot_at_end": False}
        )
        with column:
            with st.expander(label, expanded=False):
                axis_label = st.radio(
                    "Orientação da perna", ("Horizontal", "Vertical"),
                    index=0 if setting["axis"] == "horizontal" else 1,
                    horizontal=True, key=f"part_axis_v4_{item_key}_{side}",
                )
                axis = axis_label.lower()
                directions = (("Esquerda", "Direita") if axis == "horizontal"
                              else ("Cima", "Baixo"))
                direction = st.radio(
                    "Onde começa a coxa", directions,
                    index=0 if setting["foot_at_end"] else 1,
                    horizontal=True,
                    key=f"part_direction_v4_{item_key}_{side}_{axis}",
                )
                foot_at_end = direction == directions[0]
                setting["axis"] = axis
                setting["foot_at_end"] = foot_at_end
                cuts = setting["cuts"]
                st.caption("Posição percentual a partir da coxa.")
                first = st.slider(
                    "Fim da coxa (%)", 1, 99, cuts[0],
                    key=f"part_thigh_v4_{item_key}_{side}_{axis}_{direction}",
                )
                second = st.slider(
                    "Fim do joelho (%)", 1, 99, cuts[1],
                    key=f"part_knee_v4_{item_key}_{side}_{axis}_{direction}",
                )
                third = st.slider(
                    "Fim da canela (%)", 1, 99, cuts[2],
                    key=f"part_shin_v4_{item_key}_{side}_{axis}_{direction}",
                )
                if first < second < third:
                    setting["cuts"] = [first, second, third]
                else:
                    st.error("Os percentuais devem crescer da coxa ao pé.")
                    invalid_cuts = True
    part_metrics = {}
    for side in LEGS.values():
        setting = settings[side]
        part_metrics[side], _ = leg_part_metrics(
            analysis["temperatures"], analysis["masks"][side], threshold,
            tuple(setting["cuts"]), axis=setting["axis"],
            foot_at_end=setting["foot_at_end"],
        )

    st.markdown("##### Segmentação das pernas")
    st.caption("Na prévia: 1 coxa · 2 joelho · 3 canela · 4 pé.")
    segmentation_column, temperature_column = st.columns(2, gap="medium")
    with segmentation_column:
        st.image(
            _parts_preview(image, analysis, settings),
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
                for part, part_metric in part_metrics[key].items():
                    if part_metric["total_pixels"] == 0:
                        st.write(
                            f"**{part.capitalize() if part != 'pe' else 'Pé'}:** "
                            "sem área visível; ajuste os limites."
                        )
                        continue
                    st.write(
                        f"**{part.capitalize() if part != 'pe' else 'Pé'}:** "
                        f"{part_metric['hot_pixels']:,} px quentes · "
                        f"{part_metric['total_pixels']:,} px de área · "
                        f"{part_metric['hot_percentage']:.1f}%".replace(",", ".")
                    )
    return None if invalid_cuts else metrics



__all__ = ['threshold_mode_key', 'synchronize_threshold_mode', 'load_thermography', 'image_signature', '_display_image', '_scaled_box', '_automatic_boxes', '_canvas_seeds', '_invalidate_segmentation', '_highlight_colorbar', '_parts_preview', 'edit_thermal_boxes', 'edit_thermal_mask', 'cached_temperature_scale', 'segmented_analysis', 'render_view', 'LEGS', 'VIEW_LABELS', 'DEFAULT_MIN_TEMPERATURE', 'DEFAULT_MAX_TEMPERATURE', 'DEFAULT_HOT_POSITION', 'MAX_IMAGE_SIZE', 'PERCENTAGE_MODE', 'TEMPERATURE_MODE', 'THRESHOLD_MODE_KEY']
