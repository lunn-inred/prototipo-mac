"""Caso de uso puro para analisar uma vista termográfica em memória."""

from __future__ import annotations

import io
from typing import Any, Literal

from PIL import Image, ImageOps, UnidentifiedImageError

from backend.mac_api.modules.thermography.thermal_analysis import (
    extract_temperature_scale, segmented_image,
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
    """Segmenta as pernas por watershed e calcula os pixels quentes."""
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
    result = segmented_image(image, view, minimum_temperature, maximum_temperature, threshold)
    return {key: result[key] for key in ('view', 'boxes', 'metrics')}
