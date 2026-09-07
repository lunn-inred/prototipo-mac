from __future__ import annotations

import argparse
import csv
import io
import re
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

try:
    import pypdfium2
    from img2table.document import Image as TableImage
    from img2table.ocr import TesseractOCR
    from PIL import Image, ImageOps
except ModuleNotFoundError as error:  # Pure helpers remain importable without OCR.
    pypdfium2 = None
    TableImage = None
    TesseractOCR = None
    Image = None
    ImageOps = None
    OCR_IMPORT_ERROR: ModuleNotFoundError | None = error
else:
    OCR_IMPORT_ERROR = None


META = ["_arquivo"]
DPI = 300
HEADERS = {
    8: [
        "Nome", "Posição", "Distance (km)", "High Speed Efforts",
        "Sprint Efforts", "Maximum Velocity (km/h)",
        "Player Load Per Minute", "Meterage Per Minute",
    ],
    12: [
        "Nome", "Posição", "Distance (km)", "High Speed Efforts",
        "Sprint Efforts", "Maximum Velocity (km/h)",
        "Player Load Per Minute", "Meterage Per Minute",
        "Accel&Decel Efforts", "Accel&Decel Efforts Per Minute",
        "Max Acceleration", "Max Deceleration",
    ],
}

DECIMAL = re.compile(r"^([+-]?\d+)\.(\d+)$")
LEADING_DOT = re.compile(r"^\.([+-]?\d+)\.(\d+)$")
TRAILING_DOT = re.compile(r"^([+-]?\d+)\.$")


def require_ocr_dependencies() -> None:
    if OCR_IMPORT_ERROR is not None:
        raise RuntimeError(
            "Dependencias da extracao GPS ausentes. Instale o requirements.txt. "
            f"Detalhe: {OCR_IMPORT_ERROR}"
        ) from OCR_IMPORT_ERROR


def find_tesseract() -> str:
    executable = shutil.which("tesseract")
    if not executable:
        raise RuntimeError(
            "Tesseract OCR nao encontrado. No Windows, instale o Tesseract e "
            "adicione-o ao PATH; no deploy, use o packages.txt do projeto."
        )
    return executable


def tesseract_language(executable: str) -> str:
    try:
        result = subprocess.run(
            [executable, "--list-langs"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        languages = set(result.stdout.splitlines()[1:])
    except (OSError, subprocess.SubprocessError):
        languages = set()
    if "por" in languages:
        return "por"
    if "eng" in languages:
        return "eng"
    raise RuntimeError("Tesseract encontrado, mas sem os idiomas 'por' ou 'eng'.")


def normalize_whitespace(value: Any) -> str:
    text = "" if value is None else str(value).replace("\u00a0", " ")
    text = "".join(
        " " if unicodedata.category(char).startswith("C") else char for char in text
    )
    return " ".join(text.split())


def clean_ocr_text(value: Any) -> str:
    return re.sub(r"(?<=\w)-\s+(?=\w)", "", normalize_whitespace(value))


def join_ocr_cell(words: list[dict[str, Any]]) -> str:
    text = " ".join(
        word["text"]
        for word in sorted(words, key=lambda word: (word["top"], word["left"]))
    )
    return clean_ocr_text(re.sub(r"\s+([,;:])", r"\1", text))


def prepare_cell(image: Any) -> Any:
    gray = ImageOps.grayscale(image)
    binary = gray.point(lambda pixel: 255 if pixel > 225 else 0)
    return ImageOps.expand(binary, border=10, fill=255)


def ocr_batch(
    images: list[Any],
    tesseract: str,
    language: str,
    *,
    psm: int,
    numeric: bool = False,
) -> list[tuple[str, float]]:
    prepared = [prepare_cell(image) for image in images]
    width = max(image.width for image in prepared)
    height = max(image.height for image in prepared)
    frames = []
    for image in prepared:
        frame = Image.new("L", (width, height), 255)
        frame.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
        frames.append(frame)

    with tempfile.TemporaryDirectory(prefix="extracao_pdf_ocr_") as temp:
        source = Path(temp) / "cells.tiff"
        frames[0].save(
            source,
            save_all=True,
            append_images=frames[1:],
            compression="tiff_deflate",
            dpi=(DPI, DPI),
        )
        command = [tesseract, str(source), "stdout", "-l", language, "--psm", str(psm)]
        if numeric:
            command += ["-c", "tessedit_char_whitelist=0123456789.,-"]
        result = subprocess.run(
            command + ["tsv"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )

    pages = {number: [] for number in range(1, len(images) + 1)}
    for item in csv.DictReader(io.StringIO(result.stdout), delimiter="\t"):
        text = normalize_whitespace(item.get("text"))
        if item.get("level") != "5" or not text:
            continue
        try:
            confidence, page = float(item["conf"]), int(item["page_num"])
            if confidence >= 0 and page in pages:
                pages[page].append(
                    {
                        "text": text,
                        "top": int(item["top"]),
                        "left": int(item["left"]),
                        "confidence": confidence,
                    }
                )
        except (KeyError, TypeError, ValueError):
            pass

    output = []
    for page in pages.values():
        text = join_ocr_cell(page)
        if numeric:
            text = re.sub(r"\s+", "", text)
        confidence = sum(word["confidence"] for word in page) / len(page) if page else 0
        output.append((text, confidence))
    return output


def normalize_decimal(value: str) -> tuple[str, bool]:
    match = LEADING_DOT.fullmatch(value) or DECIMAL.fullmatch(value)
    return (f"{match[1]},{match[2]}", True) if match else (value, False)


def normalize_ocr_numeric(value: str) -> tuple[str, bool]:
    match = TRAILING_DOT.fullmatch(value)
    return (f"{match[1]},0", True) if match else normalize_decimal(value)


def unique_headers(values: list[str], width: int) -> list[str]:
    headers, counts = [], {}
    for index in range(width):
        base = values[index] if index < len(values) and values[index] else f"coluna_{index + 1}"
        counts[base] = counts.get(base, 0) + 1
        headers.append(base if counts[base] == 1 else f"{base}_{counts[base]}")
    return headers


def render_page(page: Any) -> Any:
    return page.render(scale=DPI / 72).to_pil()


def image_bytes(image: Any) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def extract_with_ocr(image: Any, ocr: Any) -> list[Any]:
    return TableImage(image_bytes(image)).extract_tables(
        ocr=ocr,
        implicit_rows=False,
        implicit_columns=True,
        borderless_tables=False,
        min_confidence=1,
    )


def table_matrix(table: Any) -> list[list[str]]:
    return [[clean_ocr_text(cell.value) for cell in row] for row in table.content.values()]


def convert_table(
    table: Any,
    page_image: Any,
    source: str,
    page_number: int,
    table_number: int,
    tesseract: str,
    language: str,
) -> dict[str, Any] | None:
    detected = table_matrix(table)
    if len(detected) < 2:
        return None
    cell_rows = list(table.content.values())
    width = max(map(len, cell_rows))
    if width < 2 or sum(bool(value) for row in detected for value in row) < 4:
        return None

    detected_header = (detected[0] + [""] * width)[:width]
    headers = HEADERS.get(width, unique_headers(detected_header, width))
    data_rows = cell_rows[1:]
    values = [["" for _ in range(width)] for _ in data_rows]
    confidences = [[0.0 for _ in range(width)] for _ in data_rows]
    for column in range(width):
        crops = []
        for row in data_rows:
            if column >= len(row) or row[column] is None:
                crops.append(Image.new("RGB", (20, 20), "white"))
                continue
            bbox = row[column].bbox
            box = (int(bbox.x1) + 5, int(bbox.y1) + 5, int(bbox.x2) - 5, int(bbox.y2) - 5)
            crops.append(page_image.crop(box))
        for row_index, (text, confidence) in enumerate(
            ocr_batch(
                crops,
                tesseract,
                language,
                psm=6 if column == 0 else 7,
                numeric=column >= 2,
            )
        ):
            values[row_index][column] = text
            confidences[row_index][column] = confidence

    extracted, used_confidences = [], []
    for row_index, row in enumerate(values):
        if row == detected_header:
            continue
        for column in range(2, width):
            row[column], _ = normalize_ocr_numeric(row[column])
        if sum(bool(value) for value in row) < 2:
            continue
        extracted.append(
            {
                "_arquivo": source,
                "_pagina": page_number,
                "_tabela": table_number,
                "_linha": len(extracted) + 1,
                "dados": dict(zip(headers, row, strict=True)),
            }
        )
        used_confidences.extend(
            confidences[row_index][column]
            for column, value in enumerate(row)
            if value
        )

    if not extracted:
        return None
    bbox = table.bbox
    confidence = sum(used_confidences) / len(used_confidences) if used_confidences else 0
    return {
        "id": f"p{page_number}_t{table_number}",
        "pagina": page_number,
        "indice": table_number,
        "metodo": "img2table+tesseract-celulas",
        "bbox_pixels_300dpi": [int(bbox.x1), int(bbox.y1), int(bbox.x2), int(bbox.y2)],
        "cabecalho_detectado": detected_header,
        "cabecalhos": headers,
        "confianca_media_ocr": round(confidence, 2),
        "linhas": extracted,
    }


def extract_pdf(
    path: Path,
    ocr: Any,
    tesseract: str,
    language: str = "por",
    *,
    source_name: str | None = None,
) -> dict[str, Any]:
    source = source_name or path.name
    document = {"arquivo": source, "total_paginas": 0, "paginas_analisadas": [], "tabelas": []}
    pdf = None
    try:
        pdf = pypdfium2.PdfDocument(path)
        total = len(pdf)
        document["total_paginas"] = total
        if total == 0:
            print(f"Aviso: {source} não possui páginas.")
            return document

        indexes = list(range(max(0, total - 2), total))
        pages = [index + 1 for index in indexes]
        document["paginas_analisadas"] = pages
        for index, page_number in zip(indexes, pages, strict=True):
            try:
                image = render_page(pdf[index])
                tables = extract_with_ocr(image, ocr)
                if not tables:
                    print(f"Aviso: {source}, página {page_number}: tabela não localizada.")
                for number, table in enumerate(tables, 1):
                    converted = convert_table(
                        table, image, source, page_number, number, tesseract, language
                    )
                    if converted:
                        document["tabelas"].append(converted)
            except Exception as error:
                print(f"Aviso: {source}, página {page_number}: {error}")
    except Exception as error:
        print(f"Aviso: falha ao processar {source}: {error}")
    finally:
        if pdf is not None:
            pdf.close()

    return document


def flatten(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {**{key: row[key] for key in META}, **row["dados"]}
        for document in documents
        for table in document["tabelas"]
        for row in table["linhas"]
    ]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_bytes(csv_bytes(rows))


def csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    """Gera CSV compativel com Excel sem criar outro arquivo temporario."""
    fields, seen = META.copy(), set(META)
    for row in rows:
        for field in row:
            if field not in seen:
                fields.append(field)
                seen.add(field)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fields, delimiter=";", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def extract_uploaded_pdfs(files: list[tuple[str, bytes]]) -> list[dict[str, Any]]:
    """Executa o extrator sobre arquivos recebidos pela interface Streamlit."""
    require_ocr_dependencies()
    executable = find_tesseract()
    language = tesseract_language(executable)
    ocr = TesseractOCR(n_threads=1, lang=language, psm=11)
    documents = []
    with tempfile.TemporaryDirectory(prefix="mac_gps_upload_") as temp:
        temporary_directory = Path(temp)
        for index, (name, content) in enumerate(files, 1):
            path = temporary_directory / f"input_{index}.pdf"
            path.write_bytes(content)
            documents.append(
                extract_pdf(
                    path,
                    ocr,
                    executable,
                    language,
                    source_name=Path(name).name,
                )
            )
    return documents


def main() -> int:
    parser = argparse.ArgumentParser(description="Extrai tabelas das duas últimas páginas com img2table.")
    parser.add_argument("--entrada", type=Path, default=Path("."))
    parser.add_argument("--saida", type=Path, default=Path("saida_csv"))
    args = parser.parse_args()

    source, output = args.entrada.resolve(), args.saida.resolve()
    if not source.is_dir():
        print("Pasta de entrada indisponível.")
        return 2
    try:
        require_ocr_dependencies()
        tesseract = find_tesseract()
        language = tesseract_language(tesseract)
    except RuntimeError as error:
        print(error)
        return 2
    pdfs = sorted(source.glob("*.pdf"))
    if not pdfs:
        print("Nenhum PDF encontrado.")
        return 1

    output.mkdir(parents=True, exist_ok=True)
    ocr = TesseractOCR(n_threads=1, lang=language, psm=11)
    documents = []
    for pdf in pdfs:
        document = extract_pdf(pdf, ocr, tesseract, language)
        documents.append(document)
        write_csv(output / f"{pdf.stem}.csv", flatten([document]))

    rows = flatten(documents)
    write_csv(output / "tabelas_consolidadas.csv", rows)
    print(f"Processados {len(documents)} PDF(s): {len(rows)} linha(s) em {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
