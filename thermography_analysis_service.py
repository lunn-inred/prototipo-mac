"""Caso de uso puro para analisar uma vista termográfica em memória."""

from __future__ import annotations

import io
from typing import Any, Literal

from PIL import Image, ImageOps, UnidentifiedImageError

from thermal_analysis import (
    count_hot_pixels, detect_leg_boxes, extract_temperature_scale,
    temperature_matrix,
)

MAX_IMAGE_SIZE = 20 * 1024 * 1024
ViewName = Literal["front", "back"]


def load_thermography_image(content: bytes) -> Image.Image:
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


def extract_thermography_scale(content: bytes) -> dict[str, float]:
    """Extrai a escala impressa na imagem sem persistir o arquivo."""
    minimum_temperature, maximum_temperature = extract_temperature_scale(
        load_thermography_image(content)
    )
    return {
        "minimum_temperature": minimum_temperature,
        "maximum_temperature": maximum_temperature,
    }


def analyze_thermography_view(
    content: bytes,
    *,
    view: ViewName,
    minimum_temperature: float,
    maximum_temperature: float,
    threshold: float,
) -> dict[str, Any]:
    """Detecta as caixas e calcula os pixels quentes de uma vista."""
    if view not in {"front", "back"}:
        raise ValueError("A vista deve ser 'front' ou 'back'.")
    minimum_temperature = float(minimum_temperature)
    maximum_temperature = float(maximum_temperature)
    threshold = float(threshold)
    if maximum_temperature <= minimum_temperature:
        raise ValueError("Tmax deve ser maior que Tmin.")
    if not minimum_temperature <= threshold <= maximum_temperature:
        raise ValueError("O limiar deve estar entre Tmin e Tmax.")

    image = load_thermography_image(content)
    detected_boxes = detect_leg_boxes(image)
    if len(detected_boxes) != 2:
        raise ValueError(
            "Não foi possível identificar exatamente duas caixas R1/R2 "
            f"({len(detected_boxes)} encontrada(s))."
        )

    if view == "front":
        boxes = {"right": detected_boxes[0], "left": detected_boxes[1]}
    else:
        boxes = {"left": detected_boxes[0], "right": detected_boxes[1]}

    temperatures = temperature_matrix(
        image, minimum_temperature, maximum_temperature
    )
    metrics: dict[str, dict[str, float | int]] = {}
    for side, box in boxes.items():
        hot_pixels, total_pixels = count_hot_pixels(temperatures, box, threshold)
        metrics[side] = {
            "hot_pixels": hot_pixels,
            "total_pixels": total_pixels,
            "hot_percentage": hot_pixels / total_pixels * 100,
            "threshold": threshold,
        }
    return {"view": view, "boxes": boxes, "metrics": metrics}
