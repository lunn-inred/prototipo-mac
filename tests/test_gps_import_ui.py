from copy import deepcopy
from io import BytesIO
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from gps_extraction import EXTRACTION_VERSION


APP = "from gps_import_ui import render_gps_import\nrender_gps_import()"


class GpsExtractionVersionTests(unittest.TestCase):
    def test_failed_reextraction_keeps_old_results_and_edits(self):
        app = AppTest.from_string(APP)
        app.session_state["gps_extraction_open"] = True
        documents = [{"arquivo": "antigo.pdf", "versao_extrator": 0}]
        edits = {0: [{"atleta": "corrigido"}]}
        app.session_state["gps_extraction_documents"] = deepcopy(documents)
        app.session_state["gps_extraction_edited"] = deepcopy(edits)
        upload = BytesIO(b"pdf")
        upload.name = "novo.pdf"
        with patch("gps_import_ui.st.file_uploader", return_value=[upload]), patch(
            "gps_import_ui.extract_uploaded_pdfs", side_effect=RuntimeError("falha simulada")
        ):
            app.run()
            app.button(key="gps_extract_button").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertIn("falha simulada", app.error[0].value)
        self.assertEqual(app.session_state["gps_extraction_documents"], documents)
        self.assertEqual(app.session_state["gps_extraction_edited"], edits)
        self.assertFalse(any(button.label == "Validar para envio" for button in app.button))

    def test_old_or_mixed_sessions_preserve_data_and_block_actions(self):
        for version in (None, EXTRACTION_VERSION - 1):
            with self.subTest(version=version):
                documents = [
                    {"origem_metadados": "cabecalho_pagina", "versao_extrator": EXTRACTION_VERSION},
                    {"origem_metadados": "cabecalho_pagina", "versao_extrator": version},
                ]
                state = {
                    "gps_extraction_open": True,
                    "gps_extraction_documents": documents,
                    "gps_extraction_edited": {0: [{"atleta": "corrigido"}]},
                    "gps_import_validation": {"signature": "anterior", "previews": []},
                    "gps_import_results": ["anterior"],
                }
                app = AppTest.from_string(APP)
                for key, value in state.items():
                    app.session_state[key] = deepcopy(value)
                with patch("gps_import_ui.preview_gps_documents") as validate, patch(
                    "gps_import_ui.import_gps_documents"
                ) as send:
                    app.run()
                self.assertEqual(len(app.exception), 0)
                self.assertIn("versão anterior", app.info[0].value)
                self.assertFalse(any(button.label in ("Validar para envio", "Confirmar envio ao banco") for button in app.button))
                for key, value in state.items():
                    self.assertEqual(app.session_state[key], value)
                validate.assert_not_called()
                send.assert_not_called()

    def test_current_extraction_reaches_review(self):
        app = AppTest.from_string(APP)
        app.session_state["gps_extraction_open"] = True
        app.session_state["gps_extraction_documents"] = [{
            "arquivo": "relatorio.pdf", "origem_metadados": "cabecalho_pagina",
            "versao_extrator": EXTRACTION_VERSION, "paginas_analisadas": [5, 6],
            "tabelas": [{"linhas": [{"_arquivo": "relatorio.pdf", "dados": {
                "Nome": "CAIO", "Posição": "ATA", "Distance (km)": "5,2",
            }}]}],
        }]
        app.run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any(button.label == "Validar para envio" for button in app.button))


if __name__ == "__main__":
    unittest.main()
