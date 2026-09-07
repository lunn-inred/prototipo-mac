import unittest

from gps_extraction import csv_bytes, flatten, normalize_ocr_numeric


class GpsExtractionTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
