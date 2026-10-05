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


def _boolean_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    padded = np.r_[False, mask.astype(bool), False]
    changes = np.flatnonzero(padded[1:] != padded[:-1])
    return list(zip(changes[::2], changes[1::2]))


def detect_colorbar_box(image: Image.Image) -> tuple[dict[str, int], float]:
    """Localiza a barra térmica vertical pela continuidade e variação cromática."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    height, width = rgb.shape[:2]
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # Caso preferencial da HIKMICRO: duas bordas verticais claras em torno da barra.
    right_offset = int(width * .60)
    edges = cv2.Canny(gray[:, right_offset:], 80, 180)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=max(35, height // 10),
        minLineLength=int(height * .24), maxLineGap=18,
    )
    verticals: list[tuple[int, int, int]] = []
    if lines is not None:
        for x1, y1, x2, y2 in lines.reshape(-1, 4):
            if abs(int(x2) - int(x1)) <= 4:
                verticals.append((
                    right_offset + (int(x1) + int(x2)) // 2,
                    min(int(y1), int(y2)), max(int(y1), int(y2)),
                ))
    candidates = []
    for index, first in enumerate(verticals):
        for second in verticals[index + 1:]:
            left_line, right_line = sorted((first, second))
            separation = right_line[0] - left_line[0]
            overlap = min(left_line[2], right_line[2]) - max(left_line[1], right_line[1])
            if 8 <= separation <= max(28, int(width * .05)) and overlap > height * .12:
                candidates.append((left_line, right_line, overlap))
    if candidates:
        left_line, right_line, overlap = max(
            candidates, key=lambda item: (item[0][0] + item[1][0], item[2])
        )
        left, right = left_line[0] + 1, right_line[0]
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        inner = hsv[:, left:right]
        saturation = np.median(inner[:, :, 1], axis=1)
        value = np.median(inner[:, :, 2], axis=1)
        colorful = (saturation > 30) & (value > 55)
        colorful[:int(height * .04)] = False
        colorful[int(height * .92):] = False
        runs = [pair for pair in _boolean_runs(colorful) if pair[1] - pair[0] > height * .20]
        if runs:
            top, bottom = max(runs, key=lambda pair: pair[1] - pair[0])
            extension = int((bottom - top) * .14)
            top, bottom = max(0, top - extension), min(height, bottom + extension)
            return {
                "left": int(left), "top": int(top),
                "width": int(right - left), "height": int(bottom - top),
            }, float(np.clip(.65 + overlap / height, 0, 1))

    # Fallback cromático: procura, no lado direito, colunas com grande amplitude
    # de cor vertical e pouca variação horizontal.
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    x_start, x_end = int(width * .60), int(width * .985)
    y_start, y_end = int(height * .08), int(height * .92)
    crop = lab[y_start:y_end, x_start:x_end]
    vertical_change = np.linalg.norm(np.diff(crop, axis=0), axis=2).mean(axis=0)
    horizontal_change = np.linalg.norm(np.diff(crop, axis=1), axis=2).mean(axis=0)
    horizontal_change = np.r_[horizontal_change, horizontal_change[-1]]
    chroma = crop[:, :, 1:]
    amplitude = np.linalg.norm(
        np.percentile(chroma, 95, axis=0) - np.percentile(chroma, 5, axis=0), axis=1
    )
    score = amplitude + 4 * vertical_change - .6 * horizontal_change
    peak = int(np.argmax(score))
    cutoff = max(float(score[peak]) * .42, float(np.percentile(score, 80)))
    left, right = peak, peak + 1
    while left > 0 and score[left - 1] >= cutoff and peak - left < 24:
        left -= 1
    while right < len(score) and score[right] >= cutoff and right - peak < 24:
        right += 1
    if right - left < 4:
        left, right = max(0, peak - 5), min(len(score), peak + 6)
    box = {
        "left": x_start + left, "top": y_start,
        "width": right - left, "height": y_end - y_start,
    }
    confidence = float(np.clip(
        (score[peak] - np.median(score)) / (np.std(score) * 4 + 1e-6), 0, 1
    ))
    return box, confidence


def extract_colorbar(
    image: Image.Image,
    box: Mapping[str, int | float] | None = None,
) -> np.ndarray:
    """Extrai a paleta vertical da caixa detectada ou corrigida pelo usuário."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    height, width = rgb.shape[:2]
    if box is None:
        box, _confidence = detect_colorbar_box(image)
    left = max(0, min(width - 1, int(box["left"])))
    top = max(0, min(height - 1, int(box["top"])))
    right = max(left + 1, min(width, left + int(box["width"])))
    bottom = max(top + 1, min(height, top + int(box["height"])))
    lateral_padding = max(1, int(round((right - left) * .16)))
    inner_left, inner_right = left + lateral_padding, right - lateral_padding
    if inner_right <= inner_left:
        inner_left, inner_right = left, right
    strip = rgb[top:bottom, inner_left:inner_right]
    if strip.size == 0:
        raise ValueError("Não foi possível extrair a barra térmica da imagem.")
    return np.median(strip, axis=1).astype(np.uint8)


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
    colorbar_box: Mapping[str, int | float] | None = None,
) -> np.ndarray:
    """Mapeia os pixels RGB à barra da imagem e retorna temperaturas em °C."""
    if maximum_temperature <= minimum_temperature:
        raise ValueError("Tmax deve ser maior que Tmin.")
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    palette = extract_colorbar(image, colorbar_box)
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


def normalize_binary_region(
    mask: np.ndarray,
    box: Mapping[str, int | float],
    canvas_size: tuple[int, int] = (180, 320),
) -> np.ndarray:
    """Normaliza uma máscara recortada sem distorcer sua proporção.

    ``canvas_size`` usa a ordem (largura, altura). A interpolação por vizinho
    mais próximo preserva o caráter binário da máscara.
    """
    cropped = matrix_region(np.asarray(mask, dtype=bool), box).astype(np.uint8)
    canvas_width, canvas_height = canvas_size
    if canvas_width <= 0 or canvas_height <= 0:
        raise ValueError("As dimensões do mapa comparativo devem ser positivas.")
    scale = min(canvas_width / cropped.shape[1], canvas_height / cropped.shape[0])
    resized_width = max(1, int(round(cropped.shape[1] * scale)))
    resized_height = max(1, int(round(cropped.shape[0] * scale)))
    resized = cv2.resize(
        cropped, (resized_width, resized_height), interpolation=cv2.INTER_NEAREST
    ).astype(bool)
    canvas = np.zeros((canvas_height, canvas_width), dtype=bool)
    offset_x = (canvas_width - resized_width) // 2
    offset_y = (canvas_height - resized_height) // 2
    canvas[
        offset_y:offset_y + resized_height,
        offset_x:offset_x + resized_width,
    ] = resized
    return canvas


def compare_hot_masks(
    baseline_mask: np.ndarray,
    current_mask: np.ndarray,
    baseline_box: Mapping[str, int | float],
    current_box: Mapping[str, int | float],
    canvas_size: tuple[int, int] = (180, 320),
) -> dict[str, Image.Image | int]:
    """Compara máscaras quentes T0/Ti em uma geometria normalizada comum."""
    baseline = normalize_binary_region(baseline_mask, baseline_box, canvas_size)
    current = normalize_binary_region(current_mask, current_box, canvas_size)
    persistent = baseline & current
    new = ~baseline & current
    resolved = baseline & ~current

    preview = np.full((*baseline.shape, 3), 18, dtype=np.uint8)
    preview[resolved] = (42, 136, 255)   # azul: deixou de estar quente
    preview[persistent] = (255, 196, 0)  # amarelo: permaneceu quente
    preview[new] = (239, 68, 68)         # vermelho: novo pixel quente
    return {
        "image": Image.fromarray(preview),
        "new_pixels": int(np.count_nonzero(new)),
        "persistent_pixels": int(np.count_nonzero(persistent)),
        "resolved_pixels": int(np.count_nonzero(resolved)),
    }


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


def hot_pixels_overlay(
    image: Image.Image,
    temperature_map: np.ndarray,
    masks: Mapping[str, np.ndarray],
    threshold: float,
) -> Image.Image:
    """Mantém visíveis somente os pixels quentes das áreas segmentadas."""
    original = np.asarray(image.convert("RGB"), dtype=np.uint8)
    union = np.zeros(original.shape[:2], dtype=bool)
    for mask in masks.values():
        union |= mask.astype(bool)
    hot = union & np.isfinite(temperature_map) & (temperature_map >= threshold)
    preview = np.zeros_like(original)
    preview[hot] = original[hot]
    return Image.fromarray(preview)
