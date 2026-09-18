import io
import unittest

import cv2
import numpy as np
from PIL import Image

from legacy_thermography import (
    detect_table_grid,
    document_pages,
    extract_document,
    extract_date,
    match_athlete,
    parse_number,
)


class LegacyThermographyTests(unittest.TestCase):
    def test_parses_localized_numbers(self) -> None:
        self.assertEqual(parse_number("72,5"), 72.5)
        self.assertEqual(parse_number("1.250", integer=True), 1250)
        self.assertIsNone(parse_number("ilegível"))

    def test_extracts_and_validates_date(self) -> None:
        self.assertEqual(extract_date("DATA: 22/06/2026"), "2026-06-22")
        self.assertIsNone(extract_date("DATA: 42/18/2026"))

    def test_matches_alternative_athlete_name(self) -> None:
        athletes = [
            {
                "id_atleta": 4,
                "nome": "Felipe Cruz",
                "apelido": "Cruz",
                "nome_alternativo": "CRUZ, FELIPE",
            }
        ]
        athlete_id, label, confidence = match_athlete("Felipe", athletes)
        self.assertEqual(athlete_id, 4)
        self.assertEqual(label, "Cruz")
        self.assertEqual(confidence, 1.0)

    def test_does_not_force_weak_athlete_match(self) -> None:
        athletes = [
            {
                "id_atleta": 4,
                "nome": "Felipe Cruz",
                "apelido": "Cruz",
                "nome_alternativo": "",
            }
        ]
        athlete_id, _, confidence = match_athlete("XYZ", athletes)
        self.assertIsNone(athlete_id)
        self.assertLess(confidence, 0.72)

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

        pages = extract_document(buffer.getvalue(), "ficha.png", [])

        self.assertEqual(len(pages), 1)
        self.assertTrue(pages[0]["error"])
        self.assertEqual(pages[0]["rows"], [])
        self.assertIsInstance(pages[0]["diagnostic"], Image.Image)


if __name__ == "__main__":
    unittest.main()
