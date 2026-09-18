"""Extração local e revisável de fichas manuscritas de termografia."""

from __future__ import annotations

import io
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Callable
from unicodedata import combining, normalize

import cv2
import numpy as np
import pypdfium2 as pdfium
import pytesseract
from PIL import Image, ImageOps
from pytesseract import Output


EXPECTED_COLUMNS = (
    "numero",
    "apelido",
    "massa",
    "eva_dor",
    "frente",
    "verso",
    "observacoes",
)
NUMERIC_COLUMNS = {"numero", "massa", "eva_dor", "frente", "verso"}
DATE_PATTERN = re.compile(
    r"(?<!\d)([0-3]?\d)[/\-.]([01]?\d)[/\-.]((?:19|20)?\d{2})(?!\d)"
)


def document_pages(content: bytes, filename: str) -> list[Image.Image]:
    """Converte uma imagem ou PDF em páginas RGB mantidas somente em memória."""
    if not content:
        raise ValueError("O documento está vazio.")
    if filename.lower().endswith(".pdf"):
        document = pdfium.PdfDocument(content)
        pages = [
            page.render(scale=2.4).to_pil().convert("RGB")
            for page in document
        ]
        if not pages:
            raise ValueError("O PDF não possui páginas.")
        return pages
    try:
        with Image.open(io.BytesIO(content)) as source:
            source.load()
            return [ImageOps.exif_transpose(source).convert("RGB")]
    except OSError as error:
        raise ValueError("O arquivo não é uma imagem ou PDF válido.") from error


def _ordered_quad(points: np.ndarray) -> np.ndarray:
    points = points.astype(np.float32)
    ordered = np.zeros((4, 2), dtype=np.float32)
    coordinate_sum = points.sum(axis=1)
    coordinate_difference = np.diff(points, axis=1).ravel()
    ordered[0] = points[np.argmin(coordinate_sum)]
    ordered[2] = points[np.argmax(coordinate_sum)]
    ordered[1] = points[np.argmin(coordinate_difference)]
    ordered[3] = points[np.argmax(coordinate_difference)]
    return ordered


def rectify_document(image: Image.Image) -> Image.Image:
    """Recorta a maior folha quadrilateral e corrige sua perspectiva."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    edges = cv2.morphologyEx(
        edges, cv2.MORPH_CLOSE, np.ones((7, 7), dtype=np.uint8)
    )
    contours, _ = cv2.findContours(
        edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
    )
    page_area = rgb.shape[0] * rgb.shape[1]
    quadrilateral = None
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        if cv2.contourArea(contour) < page_area * 0.22:
            break
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(polygon) == 4:
            quadrilateral = _ordered_quad(polygon.reshape(4, 2))
            break
    if quadrilateral is None:
        return image.convert("RGB")

    top_left, top_right, bottom_right, bottom_left = quadrilateral
    width = int(
        max(
            np.linalg.norm(bottom_right - bottom_left),
            np.linalg.norm(top_right - top_left),
        )
    )
    height = int(
        max(
            np.linalg.norm(top_right - bottom_right),
            np.linalg.norm(top_left - bottom_left),
        )
    )
    if width < 100 or height < 100:
        return image.convert("RGB")
    destination = np.asarray(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(quadrilateral, destination)
    rectified = cv2.warpPerspective(
        rgb, transform, (width, height), borderValue=(255, 255, 255)
    )
    return Image.fromarray(rectified)


def prepare_page(image: Image.Image) -> tuple[Image.Image, np.ndarray]:
    """Normaliza resolução e gera binarização apropriada à detecção da grade."""
    page = rectify_document(image)
    rgb = np.asarray(page, dtype=np.uint8)
    if rgb.shape[1] < 1600:
        scale = 1600 / rgb.shape[1]
        rgb = cv2.resize(
            rgb,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        35,
        12,
    )
    return Image.fromarray(rgb), binary


def _cluster_positions(indexes: np.ndarray) -> list[int]:
    if indexes.size == 0:
        return []
    clusters: list[list[int]] = [[int(indexes[0])]]
    for position in indexes[1:]:
        position = int(position)
        if position <= clusters[-1][-1] + 3:
            clusters[-1].append(position)
        else:
            clusters.append([position])
    return [round(sum(cluster) / len(cluster)) for cluster in clusters]


def table_grid_mask(binary: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Realça as linhas horizontais e verticais candidatas da tabela."""
    height, width = binary.shape
    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(25, width // 28), 1)
    )
    vertical_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (1, max(25, height // 28))
    )
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel)
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel)
    return horizontal, vertical, cv2.bitwise_or(horizontal, vertical)


def detect_table_grid(binary: np.ndarray) -> tuple[list[int], list[int], np.ndarray]:
    """Detecta as oito divisórias verticais e linhas horizontais da tabela."""
    height, width = binary.shape
    horizontal, vertical, grid = table_grid_mask(binary)

    x_scores = np.count_nonzero(vertical, axis=0)
    y_scores = np.count_nonzero(horizontal, axis=1)
    x_positions = _cluster_positions(
        np.flatnonzero(x_scores >= max(20, int(height * 0.12)))
    )
    y_positions = _cluster_positions(
        np.flatnonzero(y_scores >= max(30, int(width * 0.25)))
    )

    # A ficha tem sete colunas, portanto deve possuir oito divisórias.
    if len(x_positions) > 8:
        candidates = []
        for start in range(len(x_positions) - 7):
            sequence = x_positions[start:start + 8]
            gaps = np.diff(sequence)
            if np.all(gaps > width * 0.025):
                candidates.append((sequence[-1] - sequence[0], sequence))
        if candidates:
            x_positions = max(candidates, key=lambda item: item[0])[1]

    if len(x_positions) != 8:
        raise ValueError(
            "Não foi possível identificar as sete colunas da tabela "
            f"({max(0, len(x_positions) - 1)} encontrada(s))."
        )

    x1, x2 = x_positions[0], x_positions[-1]
    y_positions = [
        position
        for position in y_positions
        if np.count_nonzero(horizontal[position, x1:x2 + 1]) >= (x2 - x1) * 0.45
    ]
    if len(y_positions) < 3:
        raise ValueError("Não foi possível identificar as linhas da tabela.")

    return x_positions, y_positions, grid


def diagnostic_image(page: Image.Image, grid: np.ndarray) -> Image.Image:
    """Sobrepõe à página as linhas candidatas encontradas pelo detector."""
    diagnostic = np.asarray(page).copy()
    diagnostic[grid > 0] = (0, 180, 80)
    return Image.fromarray(diagnostic)


def _cell_images(
    page: Image.Image,
    binary: np.ndarray,
    box: tuple[int, int, int, int],
) -> tuple[Image.Image, Image.Image]:
    left, top, right, bottom = box
    pad_x = max(2, int((right - left) * 0.025))
    pad_y = max(2, int((bottom - top) * 0.08))
    left, right = left + pad_x, right - pad_x
    top, bottom = top + pad_y, bottom - pad_y
    color_crop = page.crop((left, top, right, bottom))
    threshold_crop = binary[top:bottom, left:right]
    threshold_crop = cv2.bitwise_not(threshold_crop)
    return color_crop, Image.fromarray(threshold_crop)


def _ocr_variant(
    image: Image.Image,
    *,
    numeric: bool,
    multiline: bool,
) -> tuple[str, float]:
    config = f"--oem 1 --psm {6 if multiline else 7}"
    if numeric:
        config += " -c tessedit_char_whitelist=0123456789,.-"
    data = pytesseract.image_to_data(
        image,
        lang="por+eng",
        config=config,
        output_type=Output.DICT,
    )
    words = []
    confidences = []
    for text, confidence in zip(data["text"], data["conf"]):
        text = str(text).strip()
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            confidence_value = -1
        if text:
            words.append(text)
            if confidence_value >= 0:
                confidences.append(confidence_value)
    return " ".join(words).strip(), (
        sum(confidences) / len(confidences) if confidences else 0.0
    )


def recognize_cell(
    color_image: Image.Image,
    threshold_image: Image.Image,
    column: str,
) -> tuple[str, float]:
    """Executa OCR em duas variantes e conserva o resultado mais confiante."""
    numeric = column in NUMERIC_COLUMNS
    multiline = column == "observacoes"
    candidates = [
        _ocr_variant(color_image, numeric=numeric, multiline=multiline),
        _ocr_variant(threshold_image, numeric=numeric, multiline=multiline),
    ]
    return max(candidates, key=lambda candidate: candidate[1])


def parse_number(text: str, *, integer: bool = False) -> float | int | None:
    cleaned = re.sub(r"[^0-9,.-]", "", text).strip()
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    else:
        if (
            integer
            and ("." in cleaned or "," in cleaned)
            and len(re.split(r"[.,]", cleaned)[-1]) == 3
        ):
            cleaned = cleaned.replace(".", "").replace(",", "")
        else:
            cleaned = cleaned.replace(",", ".")
    try:
        number = float(cleaned)
    except ValueError:
        return None
    return int(round(number)) if integer else number


def extract_date(text: str) -> str | None:
    match = DATE_PATTERN.search(text)
    if not match:
        return None
    day, month, year = match.groups()
    if len(year) == 2:
        year = f"20{year}"
    try:
        return datetime(int(year), int(month), int(day)).date().isoformat()
    except ValueError:
        return None


def normalized_name(value: str) -> str:
    decomposed = normalize("NFKD", value.casefold().strip())
    return "".join(
        character
        for character in decomposed
        if not combining(character) and character.isalnum()
    )


def match_athlete(
    extracted_name: str,
    athletes: list[dict[str, object]],
) -> tuple[int | None, str, float]:
    """Relaciona o apelido extraído aos nomes conhecidos, sem forçar ambiguidades."""
    target = normalized_name(extracted_name)
    if not target:
        return None, "", 0.0

    best_id = None
    best_label = ""
    best_score = 0.0
    for athlete in athletes:
        alternatives = [
            str(athlete.get("nome") or ""),
            str(athlete.get("apelido") or ""),
        ]
        alternatives.extend(
            part.strip()
            for part in str(athlete.get("nome_alternativo") or "").split(",")
        )
        for alternative in alternatives:
            normalized = normalized_name(alternative)
            if not normalized:
                continue
            score = (
                1.0
                if normalized == target
                else SequenceMatcher(None, target, normalized).ratio()
            )
            if score > best_score:
                best_score = score
                best_id = int(athlete["id_atleta"])
                best_label = (
                    str(athlete.get("apelido") or "").strip()
                    or str(athlete.get("nome") or "").strip()
                )

    # Resultados fracos permanecem sem associação para revisão humana.
    if best_score < 0.72:
        return None, "", best_score
    return best_id, best_label, best_score


def extract_page(
    image: Image.Image,
    athletes: list[dict[str, object]],
    ocr: Callable[
        [Image.Image, Image.Image, str], tuple[str, float]
    ] = recognize_cell,
) -> dict[str, object]:
    """Extrai uma página e retorna linhas, data e diagnóstico visual."""
    page, binary = prepare_page(image)
    x_positions, y_positions, grid = detect_table_grid(binary)

    header_bottom = y_positions[0]
    header_image = page.crop((0, 0, page.width, max(1, header_bottom)))
    header_text, _ = _ocr_variant(
        header_image, numeric=False, multiline=True
    )
    collection_date = extract_date(header_text)

    rows = []
    # O primeiro intervalo corresponde ao cabeçalho da tabela.
    for row_index in range(1, len(y_positions) - 1):
        top, bottom = y_positions[row_index], y_positions[row_index + 1]
        if bottom - top < 14:
            continue
        raw: dict[str, str] = {}
        confidence: dict[str, float] = {}
        for column_index, column in enumerate(EXPECTED_COLUMNS):
            box = (
                x_positions[column_index],
                top,
                x_positions[column_index + 1],
                bottom,
            )
            color_cell, threshold_cell = _cell_images(page, binary, box)
            raw[column], confidence[column] = ocr(
                color_cell, threshold_cell, column
            )

        if not any(raw.values()):
            continue
        athlete_id, athlete_name, match_score = match_athlete(
            raw["apelido"], athletes
        )
        mass = parse_number(raw["massa"])
        eva = parse_number(raw["eva_dor"], integer=True)
        front = parse_number(raw["frente"], integer=True)
        back = parse_number(raw["verso"], integer=True)
        issues = []
        if athlete_id is None:
            issues.append("Jogador não identificado")
        if mass is None or mass <= 0:
            issues.append("Massa inválida")
        if eva is None or not 0 <= eva <= 10:
            issues.append("EVA deve estar entre 0 e 10")
        if front is None or front < 0:
            issues.append("Frente inválida")
        if back is None or back < 0:
            issues.append("Verso inválido")
        if collection_date is None:
            issues.append("Data não identificada")

        rows.append(
            {
                "id_atleta": athlete_id,
                "Jogador": athlete_name or raw["apelido"],
                "Massa": mass,
                "EVA Dor": eva,
                "Frente": front,
                "Verso": back,
                "Observações": raw["observacoes"],
                "Data": collection_date,
                "Confiança jogador": round(match_score * 100, 1),
                "Confiança OCR": round(
                    sum(confidence.values()) / len(confidence), 1
                ),
                "Revisão": "; ".join(issues) if issues else "Pronto para revisão",
                "_raw": raw,
            }
        )

    return {
        "date": collection_date,
        "header_text": header_text,
        "rows": rows,
        "diagnostic": diagnostic_image(page, grid),
        "error": None,
    }


def extract_document(
    content: bytes,
    filename: str,
    athletes: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Processa todas as páginas de um documento."""
    results = []
    for source_page in document_pages(content, filename):
        try:
            results.append(extract_page(source_page, athletes))
        except Exception as error:
            # Mantém um diagnóstico visual mesmo quando a validação estrita
            # da grade falha, para mostrar ao usuário o que foi detectado.
            try:
                page, binary = prepare_page(source_page)
                _, _, grid = table_grid_mask(binary)
                diagnostic = diagnostic_image(page, grid)
            except Exception:
                diagnostic = source_page.convert("RGB")
            results.append(
                {
                    "date": None,
                    "header_text": "",
                    "rows": [],
                    "diagnostic": diagnostic,
                    "error": str(error),
                }
            )
    return results
