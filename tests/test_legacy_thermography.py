import io
import unittest
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image

from legacy_thermography import (
    detect_table_grid,
    document_pages,
    extract_document,
    extract_date,
    extract_page,
    parse_number,
    resolve_athlete_name,
    review_rows_signature,
    validate_athlete_rows,
    validated_athlete_ids,
)


class LegacyThermographyTests(unittest.TestCase):
    def test_parses_localized_numbers(self) -> None:
        self.assertEqual(parse_number("72,5"), 72.5)
        self.assertEqual(parse_number("1.250", integer=True), 1250)
        self.assertIsNone(parse_number("ilegível"))

    def test_extracts_and_validates_date(self) -> None:
        self.assertEqual(extract_date("DATA: 22/06/2026"), "2026-06-22")
        self.assertIsNone(extract_date("DATA: 42/18/2026"))

    def test_resolves_normalized_name_nickname_and_alternative(self) -> None:
        athletes = [
            {
                "id_atleta": 4,
                "nome": "Felipe Cruz",
                "apelido": "Cruz",
                "nome_alternativo": "F. Cruz, Felipe",
            }
        ]

        for entered_name in ("felipe cruz", "CRÚZ", "f cruz", "FELIPE"):
            with self.subTest(entered_name=entered_name):
                athlete_id, label, error = resolve_athlete_name(
                    entered_name, athletes
                )
                self.assertEqual(athlete_id, 4)
                self.assertEqual(label, "Cruz")
                self.assertIsNone(error)

    def test_rejects_empty_unknown_and_ambiguous_athlete_names(self) -> None:
        athletes = [
            {
                "id_atleta": 4,
                "nome": "Felipe Cruz",
                "apelido": "Cruz",
                "nome_alternativo": "Felipe",
            },
            {
                "id_atleta": 8,
                "nome": "Felipe Silva",
                "apelido": "Silva",
                "nome_alternativo": "Felipe",
            },
        ]

        self.assertIn("Informe", resolve_athlete_name("", athletes)[2])
        self.assertIn("não encontrado", resolve_athlete_name("XYZ", athletes)[2])
        self.assertIn("mais de um", resolve_athlete_name("Felipe", athletes)[2])
        rows = [{"Jogador": "Cruz"}, {"Jogador": "XYZ"}]
        signature = review_rows_signature(rows)
        self.assertIsNone(
            validated_athlete_ids(
                {
                    "signature": signature,
                    "resolutions": validate_athlete_rows(rows, athletes),
                },
                signature,
            )
        )

    def test_validates_every_row_and_signature_changes_after_edit(self) -> None:
        athletes = [{
            "id_atleta": 4,
            "nome": "Felipe Cruz",
            "apelido": "Cruz",
            "nome_alternativo": "",
        }]
        rows = [{"Jogador": "cruz", "Massa": 72.0}]

        validation = validate_athlete_rows(rows, athletes)
        original_signature = review_rows_signature(rows)
        edited_signature = review_rows_signature(
            [{"Jogador": "cruz", "Massa": 73.0}]
        )

        self.assertEqual(validation[0]["id_atleta"], 4)
        self.assertIsNone(validation[0]["erro"])
        self.assertNotEqual(original_signature, edited_signature)
        saved_validation = {
            "signature": original_signature,
            "resolutions": validation,
        }
        self.assertEqual(
            validated_athlete_ids(saved_validation, original_signature), [4]
        )
        self.assertIsNone(
            validated_athlete_ids(saved_validation, edited_signature)
        )

    def test_extract_page_preserves_raw_athlete_name(self) -> None:
        image = Image.new("RGB", (80, 60), "white")
        binary = np.zeros((60, 80), dtype=np.uint8)
        values = {
            "numero": "1",
            "apelido": "Felipee",
            "massa": "72",
            "eva_dor": "2",
            "frente": "30",
            "verso": "40",
            "observacoes": "ok",
        }

        def ocr(_color, _threshold, column):
            return values[column], 90.0

        with (
            patch(
                "legacy_thermography.prepare_page",
                return_value=(image, binary),
            ),
            patch(
                "legacy_thermography.detect_table_grid",
                return_value=(
                    list(range(0, 81, 10)),
                    [10, 30, 50],
                    binary,
                ),
            ),
            patch("legacy_thermography._ocr_variant", return_value=("", 0.0)),
        ):
            result = extract_page(image, ocr=ocr)

        self.assertEqual(result["rows"][0]["Jogador"], "Felipee")
        self.assertNotIn("id_atleta", result["rows"][0])

    def test_detects_expected_seven_column_grid(self) -> None:
        binary = np.zeros((600, 900), dtype=np.uint8)
        x_positions = [80, 160, 300, 400, 500, 600, 700, 820]
        y_positions = [100, 180, 260, 340, 420]
        for x in x_positions:
            cv2.line(binary, (x, 100), (x, 420), 255, 4)
        for y in y_positions:
            cv2.line(binary, (80, y), (820, y), 255, 4)

        detected_x, detected_y, _ = detect_table_grid(binary)

        self.assertEqual(len(detected_x), 8)
        self.assertEqual(len(detected_y), 5)

    def test_loads_image_document_in_memory(self) -> None:
        buffer = io.BytesIO()
        Image.new("RGB", (100, 100), "white").save(buffer, format="PNG")

        pages = document_pages(buffer.getvalue(), "ficha.png")

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].mode, "RGB")

    def test_preserves_preview_when_grid_detection_fails(self) -> None:
        buffer = io.BytesIO()
        Image.new("RGB", (500, 700), "white").save(buffer, format="PNG")

        pages = extract_document(buffer.getvalue(), "ficha.png")

        self.assertEqual(len(pages), 1)
        self.assertTrue(pages[0]["error"])
        self.assertEqual(pages[0]["rows"], [])
        self.assertIsInstance(pages[0]["diagnostic"], Image.Image)


if __name__ == "__main__":
    unittest.main()
