"""Análise aproximada de termografias HIKMICRO pseudocoloridas."""

from __future__ import annotations

from typing import Mapping

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree


def extract_colorbar(image: Image.Image) -> np.ndarray:
    """Extrai a paleta vertical do layout HIKMICRO usado no protótipo."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    height, width = rgb.shape[:2]
    strip = rgb[int(height * 0.05):int(height * 0.92), int(width * 0.96):width]
    if strip.size == 0:
        raise ValueError("Não foi possível extrair a barra térmica da imagem.")
    return strip.mean(axis=1).astype(np.uint8)


def temperature_matrix(
    image: Image.Image,
    minimum_temperature: float,
    maximum_temperature: float,
) -> np.ndarray:
    """Mapeia os pixels RGB à barra da imagem e retorna temperaturas em °C."""
    if maximum_temperature <= minimum_temperature:
        raise ValueError("Tmax deve ser maior que Tmin.")
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    palette = extract_colorbar(image)
    positions = np.linspace(1.0, 0.0, len(palette), dtype=np.float32)
    _, indexes = cKDTree(palette.astype(np.float32)).query(
        rgb.reshape(-1, 3).astype(np.float32), workers=-1
    )
    relative_temperatures = positions[indexes]
    temperatures = minimum_temperature + relative_temperatures * (
        maximum_temperature - minimum_temperature
    )
    return temperatures.reshape(rgb.shape[:2]).astype(np.float32)


def detect_leg_boxes(image: Image.Image) -> list[dict[str, int]]:
    """Detecta as duas caixas brancas R1/R2 do layout HIKMICRO atual."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY)
    binary = cv2.morphologyEx(
        binary, cv2.MORPH_CLOSE, np.ones((3, 3), dtype=np.uint8)
    )
    contours, _ = cv2.findContours(
        binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    height, width = gray.shape
    boxes: list[dict[str, int]] = []
    for contour in contours:
        left, top, box_width, box_height = cv2.boundingRect(contour)
        area = box_width * box_height
        aspect_ratio = box_width / box_height if box_height else 0
        if (
            area > width * height * 0.05
            and aspect_ratio > 2.0
            and box_width > width * 0.3
            and box_height > height * 0.15
        ):
            boxes.append({
                "left": int(left), "top": int(top),
                "width": int(box_width), "height": int(box_height),
            })
    boxes.sort(key=lambda box: box["top"])
    return boxes


def annotate_boxes(
    image: Image.Image, boxes: Mapping[str, Mapping[str, int]]
) -> Image.Image:
    """Desenha as regiões detectadas para conferência visual no Streamlit."""
    annotated = image.convert("RGB").copy()
    draw = ImageDraw.Draw(annotated)
    for label, box in boxes.items():
        left, top = box["left"], box["top"]
        right, bottom = left + box["width"], top + box["height"]
        draw.rectangle((left, top, right, bottom), outline="#00ff88", width=3)
        draw.text(
            (left + 6, top + 6), label, fill="#00ff88",
            stroke_fill="black", stroke_width=2,
        )
    return annotated


def matrix_region(
    matrix: np.ndarray,
    box: Mapping[str, int | float],
) -> np.ndarray:
    """Recorta uma matriz usando uma caixa expressa na resolução original."""
    height, width = matrix.shape[:2]
    left = max(0, min(width, int(box["left"])))
    top = max(0, min(height, int(box["top"])))
    right = max(left, min(width, left + int(box["width"])))
    bottom = max(top, min(height, top + int(box["height"])))
    region = matrix[top:bottom, left:right]
    if region.size == 0:
        raise ValueError("A região detectada está vazia.")
    return region


def count_hot_pixels(
    matrix: np.ndarray,
    box: Mapping[str, int | float],
    threshold: float,
) -> tuple[int, int]:
    """Retorna pixels no limiar ou acima dele e o total da região."""
    region = matrix_region(matrix, box)
    return int(np.count_nonzero(region >= threshold)), int(region.size)
