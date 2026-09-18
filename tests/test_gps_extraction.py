from types import SimpleNamespace
import unittest
from unittest.mock import patch

from gps_extraction import (
    csv_bytes,
    flatten,
    normalize_ocr_numeric,
    require_ocr_dependencies,
)


class GpsExtractionTests(unittest.TestCase):
    def test_rejects_opencv_without_required_contrib_function(self) -> None:
        incompatible_cv2 = SimpleNamespace(
            __version__="4.14.0",
            ximgproc=SimpleNamespace(),
        )

        with (
            patch("gps_extraction.OCR_IMPORT_ERROR", None),
            patch("gps_extraction.cv2", incompatible_cv2),
            self.assertRaisesRegex(RuntimeError, "niBlackThreshold"),
        ):
            require_ocr_dependencies()

    def test_accepts_opencv_with_required_contrib_function(self) -> None:
        compatible_cv2 = SimpleNamespace(
            __version__="4.14.0",
            ximgproc=SimpleNamespace(niBlackThreshold=object()),
        )

        with (
            patch("gps_extraction.OCR_IMPORT_ERROR", None),
            patch("gps_extraction.cv2", compatible_cv2),
        ):
            require_ocr_dependencies()

    def test_normalizes_common_ocr_decimals(self) -> None:
        self.assertEqual(normalize_ocr_numeric("12.34"), ("12,34", True))
        self.assertEqual(normalize_ocr_numeric("12."), ("12,0", True))
        self.assertEqual(normalize_ocr_numeric("texto"), ("texto", False))

    def test_flattens_rows_and_generates_excel_csv(self) -> None:
        documents = [
            {
                "tabelas": [
                    {
                        "linhas": [
                            {
                                "_arquivo": "teste.pdf",
                                "_pagina": 2,
                                "_tabela": 1,
                                "_linha": 1,
                                "dados": {"Nome": "Atleta", "Distance (km)": "5,2"},
                            }
                        ]
                    }
                ]
            }
        ]

        rows = flatten(documents)
        content = csv_bytes(rows)

        self.assertEqual(rows[0]["Nome"], "Atleta")
        self.assertEqual(set(rows[0]) & {"_pagina", "_tabela", "_linha"}, set())
        self.assertTrue(content.startswith(b"\xef\xbb\xbf"))
        self.assertIn(";Distance (km)".encode(), content)
        self.assertNotIn(b"_pagina", content)

    def test_csv_does_not_add_source_column_when_rows_use_view_schema(self) -> None:
        content = csv_bytes([{"atleta": "CAIO", "distance_km": 5.2}])

        self.assertIn(b"atleta;distance_km", content)
        self.assertNotIn(b"_arquivo", content)


if __name__ == "__main__":
    unittest.main()
