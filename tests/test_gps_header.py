from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from gps_header import parse_page_header
from gps_extraction import extract_pdf, flatten, read_page_header
from gps_import_service import extracted_rows_to_gps_view, prepare_gps_documents, import_gps_documents


HEADER = "RELATÓRIO DE ATIVIDADES MAC X IAPE (MD) DOMINGO, MARÇO 1, 2026 - 03:06:22 PM PÁGINA 5/6"


class GpsHeaderTests(unittest.TestCase):
    def test_real_header_preserves_seconds_and_converts_pm(self):
        self.assertEqual(parse_page_header(HEADER), {
            "equipe": "MAC", "adversario": "IAPE", "data_coleta": datetime(2026, 3, 1, 15, 6, 22),
        })

    def test_midnight_noon_and_invalid_dates(self):
        for time, hour in [("12:06:22 AM", 0), ("12:06:22 PM", 12), ("03:06:22 AM", 3)]:
            with self.subTest(time=time):
                self.assertEqual(parse_page_header(HEADER.replace("03:06:22 PM", time))["data_coleta"].hour, hour)
        for header in [HEADER.replace("MARÇO 1", "FEVEREIRO 30"), HEADER.replace("03:06:22 PM", "15:06:22 PM"), "sem cabeçalho"]:
            with self.subTest(header=header), self.assertRaises(ValueError):
                parse_page_header(header)

    def test_numeric_date_and_multiword_teams(self):
        metadata = parse_page_header("01/03/2026 16:30 SÃO JOSÉ X MAC")
        self.assertEqual(metadata["equipe"], "SÃO JOSÉ")
        self.assertEqual(metadata["data_coleta"], datetime(2026, 3, 1, 16, 30))

    def test_native_text_uses_only_first_nonempty_line(self):
        page = MagicMock()
        page.get_bbox.return_value = (0, 0, 842, 595)
        page.get_textpage.return_value.get_text_bounded.return_value = "\n" + HEADER + "\nOutra linha"
        with patch("gps_extraction.subprocess.run") as ocr:
            self.assertEqual(read_page_header(page, None, "tesseract", "por"), HEADER)
        ocr.assert_not_called()
        page.get_textpage.return_value.close.assert_called_once()

    def test_native_header_split_across_text_objects(self):
        page = MagicMock()
        page.get_bbox.return_value = (0, 0, 842, 595)
        page.get_textpage.return_value.get_text_bounded.return_value = (
            "RELATÓRIO DE ATIVIDADES\nMAC X IAPE (MD)\n"
            "DOMINGO, MARÇO 1, 2026 -\n03:06:22 PM\nPÁGINA 5/6"
        )
        with patch("gps_extraction.subprocess.run") as ocr:
            result = read_page_header(page, None, "tesseract", "por")
        self.assertEqual(parse_page_header(result), parse_page_header(HEADER))
        ocr.assert_not_called()

    def test_corrupt_native_text_falls_back_to_multiple_ocr_blocks(self):
        page = MagicMock()
        page.get_bbox.return_value = (0, 0, 842, 595)
        page.get_textpage.return_value.get_text_bounded.return_value = "RELATÓRIOEATIIAE ALIEE OIOEEREIRO IA"
        image = MagicMock(width=1000, height=1000)
        fragments = ["RELATÓRIO DE ATIVIDADES", "MAC X IAPE (MD)",
                     "DOMINGO, MARÇO 1, 2026 -", "03:06:22 PM", "PÁGINA 5/6"]
        tsv = "level\tblock_num\tpar_num\tline_num\ttext\n"
        for block, fragment in enumerate(fragments, 1):
            tsv += "".join(f"5\t{block}\t1\t1\t{word}\n" for word in fragment.split())
        with patch("gps_extraction.image_bytes", return_value=b"png"), patch(
            "gps_extraction.subprocess.run", return_value=SimpleNamespace(stdout=tsv.encode())
        ):
            result = read_page_header(page, image, "tesseract", "por")
        self.assertEqual(parse_page_header(result), parse_page_header(HEADER))

    def test_scanned_page_uses_first_ocr_line(self):
        page = MagicMock()
        page.get_textpage.return_value.get_text_bounded.return_value = ""
        image = MagicMock(width=1000, height=1000)
        tsv = "level\tblock_num\tpar_num\tline_num\ttext\n"
        tsv += "".join(f"5\t1\t1\t1\t{word}\n" for word in HEADER.split())
        tsv += "5\t1\t1\t2\tNome\n"
        with patch("gps_extraction.image_bytes", return_value=b"png"), patch(
            "gps_extraction.subprocess.run", return_value=SimpleNamespace(stdout=tsv.encode())
        ):
            self.assertEqual(read_page_header(page, image, "tesseract", "por"), HEADER)

    def test_page_metadata_flows_to_preview_and_prepared_import_with_any_filename(self):
        pdf = MagicMock()
        pdf.__len__.return_value = 6
        table = {"linhas": [{"_arquivo": "qualquer.pdf", "dados": {
            "Nome": "CAIO", "Posição": "ATA", "Distance (km)": "5,2",
        }}]}
        with (
            patch("gps_extraction.pypdfium2.PdfDocument", return_value=pdf),
            patch("gps_extraction.render_page"),
            patch("gps_extraction.extract_with_ocr", side_effect=[[object()], []]),
            patch("gps_extraction.read_page_header", return_value=HEADER),
            patch("gps_extraction.convert_table", return_value=table),
        ):
            document = extract_pdf(Path("qualquer.pdf"), None, "tesseract")
        rows = extracted_rows_to_gps_view("qualquer.pdf", flatten([document]))
        prepared = prepare_gps_documents([{"arquivo": "qualquer.pdf", "linhas": rows}])[0]
        self.assertEqual(document["erros_extracao"], [])
        self.assertEqual(prepared.errors, ())
        self.assertEqual(rows[0]["equipe"], "MAC")
        self.assertEqual(rows[0]["adversario"], "IAPE")
        self.assertEqual(prepared.metadata.collected_at, datetime(2026, 3, 1, 15, 6, 22))
        connection = MagicMock()
        with (
            patch("gps_import_service._get_or_create_group", return_value=(1, False)),
            patch("gps_import_service._get_or_create_match", return_value=(2, True)) as match,
            patch("gps_import_service._get_or_create_athlete", return_value=(3, False)),
            patch("gps_import_service._get_or_create_metric", return_value=(4, False)),
            patch("gps_import_service._fetch_duplicate_pairs", return_value=set()),
            patch("gps_import_service.execute_values") as insert,
        ):
            result = import_gps_documents([prepared], connection)[0]
        self.assertIsNone(result.error)
        self.assertEqual(match.call_args.args[1], prepared.metadata)
        self.assertEqual(insert.call_args.args[2][0][-1], datetime(2026, 3, 1, 15, 6, 22))

    def test_missing_headers_never_use_filename_and_prevent_database_access(self):
        filename = "01.02.2026_16_00h_MAC X LUMINENSE.pdf"
        rows = extracted_rows_to_gps_view(filename, [{"Nome": "CAIO", "Posição": "ATA", "Distance (km)": "5,2"}])
        prepared = prepare_gps_documents([{"arquivo": filename, "linhas": rows}])
        self.assertIsNone(rows[0]["data_coleta"])
        self.assertIsNone(prepared[0].metadata)
        connection = MagicMock()
        result = import_gps_documents(prepared, connection)[0]
        self.assertIn("cabeçalho", result.error)
        connection.assert_not_called()

    def test_different_page_headers_block_import(self):
        row = {"Nome": "CAIO", "Posição": "ATA", "Distance (km)": "5,2", **parse_page_header(HEADER)}
        other = {**row, "Nome": "JOAO", "adversario": "OUTRO"}
        prepared = prepare_gps_documents([{"arquivo": "qualquer.pdf", "linhas": [row, other]}])[0]
        self.assertIsNone(prepared.metadata)
        self.assertIn("divergentes", " ".join(prepared.errors))


if __name__ == "__main__":
    unittest.main()
