"""Conversão aproximada de imagens pseudocoloridas em dados térmicos."""

from __future__ import annotations

from functools import lru_cache
from typing import Mapping

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree


PALETTE_SIZE = 256
JET_ANCHORS = np.asarray(
    [
        (0.00, 0, 0, 128),
        (0.125, 0, 0, 255),
        (0.375, 0, 255, 255),
        (0.625, 255, 255, 0),
        (0.875, 255, 0, 0),
        (1.00, 128, 0, 0),
    ],
    dtype=np.float32,
)


@lru_cache(maxsize=1)
def reference_palette() -> np.ndarray:
    """Cria a LUT Jet temporária, ordenada da menor para a maior temperatura."""
    positions = np.linspace(0.0, 1.0, PALETTE_SIZE, dtype=np.float32)
    palette = np.column_stack(
        [
            np.interp(positions, JET_ANCHORS[:, 0], JET_ANCHORS[:, channel])
            for channel in range(1, 4)
        ]
    )
    palette.setflags(write=False)
    return palette


@lru_cache(maxsize=1)
def palette_tree() -> cKDTree:
    return cKDTree(reference_palette())


def temperature_matrix(
    image: Image.Image,
    minimum_temperature: float,
    maximum_temperature: float,
) -> np.ndarray:
    """Mapeia cada RGB à cor mais próxima da LUT e retorna temperaturas em °C."""
    if maximum_temperature <= minimum_temperature:
        raise ValueError("Tmax deve ser maior que Tmin.")

    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    pixels = rgb.reshape(-1, 3).astype(np.float32)
    _, indexes = palette_tree().query(pixels, workers=-1)
    positions = indexes.astype(np.float32) / (PALETTE_SIZE - 1)
    temperatures = minimum_temperature + positions * (
        maximum_temperature - minimum_temperature
    )
    return temperatures.reshape(rgb.shape[:2]).astype(np.float32)


def matrix_region(
    matrix: np.ndarray,
    box: Mapping[str, int | float],
) -> np.ndarray:
    """Aplica coordenadas do cropper, já expressas na resolução original."""
    height, width = matrix.shape[:2]
    left = max(0, min(width, int(box["left"])))
    top = max(0, min(height, int(box["top"])))
    right = max(left, min(width, left + int(box["width"])))
    bottom = max(top, min(height, top + int(box["height"])))
    region = matrix[top:bottom, left:right]
    if region.size == 0:
        raise ValueError("O recorte selecionado está vazio.")
    return region


def count_hot_pixels(
    matrix: np.ndarray,
    box: Mapping[str, int | float],
    threshold: float,
) -> tuple[int, int]:
    """Retorna pixels no limiar ou acima dele e o total de pixels do recorte."""
    region = matrix_region(matrix, box)
    return int(np.count_nonzero(region >= threshold)), int(region.size)
