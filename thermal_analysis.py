"""Análise aproximada de termografias HIKMICRO pseudocoloridas."""

from __future__ import annotations

from collections.abc import Callable
import math
import re
from typing import Mapping

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree


def temperature_from_scale_percentage(
    minimum_temperature: float,
    maximum_temperature: float,
    percentage: float,
) -> float:
    """Converte uma posicao percentual da escala termica em graus Celsius."""
    minimum_temperature = float(minimum_temperature)
    maximum_temperature = float(maximum_temperature)
    percentage = float(percentage)
    if not all(map(math.isfinite, (
        minimum_temperature, maximum_temperature, percentage,
    ))):
        raise ValueError("A escala e a porcentagem devem ser valores finitos.")
    if maximum_temperature <= minimum_temperature:
        raise ValueError("Tmax deve ser maior que Tmin.")
    if not 0.0 <= percentage <= 100.0:
        raise ValueError("A porcentagem deve estar entre 0% e 100%.")
    return minimum_temperature + percentage / 100.0 * (
        maximum_temperature - minimum_temperature
    )


def scale_percentage_from_temperature(
    minimum_temperature: float,
    maximum_temperature: float,
    temperature: float,
) -> float:
    """Converte uma temperatura em sua posicao percentual na escala termica."""
    minimum_temperature = float(minimum_temperature)
    maximum_temperature = float(maximum_temperature)
    temperature = float(temperature)
    if not all(map(math.isfinite, (
        minimum_temperature, maximum_temperature, temperature,
    ))):
        raise ValueError("A escala e a temperatura devem ser valores finitos.")
    if maximum_temperature <= minimum_temperature:
        raise ValueError("Tmax deve ser maior que Tmin.")
    if not minimum_temperature <= temperature <= maximum_temperature:
        raise ValueError("A temperatura deve estar entre Tmin e Tmax.")
    return (temperature - minimum_temperature) / (
        maximum_temperature - minimum_temperature
    ) * 100.0


def extract_colorbar(image: Image.Image) -> np.ndarray:
    """Extrai a paleta vertical do layout HIKMICRO usado no protótipo."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    height, width = rgb.shape[:2]
    strip = rgb[int(height * 0.05):int(height * 0.92), int(width * 0.96):width]
    if strip.size == 0:
        raise ValueError("Não foi possível extrair a barra térmica da imagem.")
    return strip.mean(axis=1).astype(np.uint8)


def _temperature_number(text: str) -> float | None:
    """Extrai o primeiro número decimal plausível retornado pelo OCR."""
    match = re.search(r"\d{1,3}[.,]\d{1,2}", text)
    if match is None:
        return None
    value = float(match.group(0).replace(",", "."))
    return value if -50.0 <= value <= 200.0 else None


def extract_temperature_scale(
    image: Image.Image,
    ocr: Callable[[np.ndarray], str] | None = None,
) -> tuple[float, float]:
    """Lê Tmin/Tmax nas regiões usadas pelo layout HIKMICRO do protótipo.

    Reutiliza a estratégia de ``sol_ia``: Tmax no canto superior direito e
    Tmin no canto inferior direito, com binarização e OCR restrito a números.
    Retorna ``(Tmin, Tmax)`` e rejeita resultados incompletos ou invertidos.
    """
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    height, width = rgb.shape[:2]
    if height < 10 or width < 10:
        raise ValueError("A imagem é pequena demais para ler a escala térmica.")

    regions = (
        rgb[int(height * 0.02):int(height * 0.25), int(width * 0.82):width],
        rgb[int(height * 0.65):int(height * 0.90), int(width * 0.82):width],
    )

    default_ocr = ocr is None
    if default_ocr:
        import pytesseract

        def ocr(processed: np.ndarray) -> str:
            return pytesseract.image_to_string(
                processed,
                config="--psm 11 -c tessedit_char_whitelist=0123456789.,",
            )

    values: list[float | None] = []
    for region in regions:
        if region.size == 0:
            values.append(None)
            continue
        gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
        enlarged = cv2.resize(
            gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC
        )
        try:
            _, threshold = cv2.threshold(
                enlarged, 200, 255, cv2.THRESH_BINARY
            )
            value = _temperature_number(ocr(threshold))
            if value is None and default_ocr:
                _, alternate = cv2.threshold(
                    enlarged, 150, 255, cv2.THRESH_BINARY
                )
                value = _temperature_number(ocr(alternate))
        except Exception as error:
            raise ValueError(
                "Não foi possível executar o OCR da escala térmica."
            ) from error
        values.append(value)

    maximum_temperature, minimum_temperature = values
    if maximum_temperature is None or minimum_temperature is None:
        raise ValueError(
            "Não foi possível reconhecer automaticamente Tmin e Tmax na imagem."
        )
    if maximum_temperature <= minimum_temperature:
        raise ValueError(
            "A escala reconhecida é inválida: Tmax deve ser maior que Tmin."
        )
    return float(minimum_temperature), float(maximum_temperature)


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
    mask: np.ndarray | None = None,
) -> tuple[int, int]:
    """Retorna pixels quentes e área total da perna segmentada."""
    region = matrix_region(matrix, box)
    if mask is None:
        return int(np.count_nonzero(region >= threshold)), int(region.size)
    mask_region = matrix_region(mask, box).astype(bool)
    if mask_region.shape != region.shape:
        raise ValueError("A máscara segmentada não corresponde à região da perna.")
    total = int(np.count_nonzero(mask_region))
    if total == 0:
        raise ValueError("A segmentação não encontrou pixels da perna.")
    return int(np.count_nonzero((region >= threshold) & mask_region)), total


def segment_leg_mask(
    image: Image.Image,
    box: Mapping[str, int | float],
    seed_mask: np.ndarray | None = None,
    iterations: int = 5,
) -> np.ndarray:
    """Segmenta a perna dentro da caixa com GrabCut e ajustes manuais opcionais.

    ``seed_mask`` usa ``1`` para inclusão, ``-1`` para exclusão e ``0`` para
    pixels ainda desconhecidos.
    """
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    height, width = rgb.shape[:2]
    left = max(0, min(width - 1, int(box["left"])))
    top = max(0, min(height - 1, int(box["top"])))
    right = max(left + 1, min(width, left + int(box["width"])))
    bottom = max(top + 1, min(height, top + int(box["height"])))
    inset = 3
    left, top = min(right - 1, left + inset), min(bottom - 1, top + inset)
    right, bottom = max(left + 1, right - inset), max(top + 1, bottom - inset)

    grabcut = np.full((height, width), cv2.GC_BGD, dtype=np.uint8)
    grabcut[top:bottom, left:right] = cv2.GC_PR_FGD
    margin = max(2, min(8, (bottom - top) // 12))
    grabcut[top:top + margin, left:right] = cv2.GC_PR_BGD
    grabcut[bottom - margin:bottom, left:right] = cv2.GC_PR_BGD

    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    patch = lab[top:bottom, left:right]
    edges = np.concatenate(
        (patch[:margin].reshape(-1, 3), patch[-margin:].reshape(-1, 3)), axis=0
    )
    background = np.median(edges, axis=0)
    distance = np.linalg.norm(patch - background, axis=2)
    local = grabcut[top:bottom, left:right]
    local[distance < 9.0] = cv2.GC_BGD
    foreground = distance > max(18.0, float(np.percentile(distance, 68)))
    border = max(5, margin)
    foreground[:border] = foreground[-border:] = False
    foreground[:, :border] = foreground[:, -border:] = False
    local[foreground] = cv2.GC_FGD

    if seed_mask is not None:
        if seed_mask.shape != (height, width):
            raise ValueError("A máscara de correção possui dimensões inválidas.")
        grabcut[seed_mask < 0] = cv2.GC_BGD
        grabcut[seed_mask > 0] = cv2.GC_FGD

    background_model = np.zeros((1, 65), np.float64)
    foreground_model = np.zeros((1, 65), np.float64)
    cv2.grabCut(
        bgr, grabcut, None, background_model, foreground_model,
        iterations, cv2.GC_INIT_WITH_MASK,
    )
    result = np.isin(grabcut, (cv2.GC_FGD, cv2.GC_PR_FGD)).astype(np.uint8)
    result[:top] = result[bottom:] = 0
    result[:, :left] = result[:, right:] = 0
    result = cv2.morphologyEx(result, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    result = cv2.morphologyEx(result, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    return result.astype(bool)


def segmentation_overlay(
    image: Image.Image,
    boxes: Mapping[str, Mapping[str, int | float]],
    masks: Mapping[str, np.ndarray],
) -> Image.Image:
    """Cria uma prévia com as máscaras segmentadas e suas caixas."""
    original = np.asarray(image.convert("RGB"), dtype=np.uint8)
    preview = np.clip(original.astype(np.float32) * 0.28, 0, 255).astype(np.uint8)
    for mask in masks.values():
        preview[mask] = original[mask]
    return annotate_boxes(Image.fromarray(preview), {
        ("Perna direita" if side == "right" else "Perna esquerda"): box
        for side, box in boxes.items()
    })
