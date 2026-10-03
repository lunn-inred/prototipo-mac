from __future__ import annotations

import io
import unittest
from datetime import date

from openpyxl import Workbook

from jump_service import extract_jump_workbook, prepare_jump_rows


class JumpWorkbookTests(unittest.TestCase):
    def workbook_bytes(self) -> bytes:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "22062026"
        sheet.append(["NOME", "APELIDO", "POSIÇÃO", "GRUPO", "PESO",
                      "CMJ1", "CMJ2", "CMJ3", "MAIOR_CMJ",
                      "SJ", "SJ", "SJ", "MAIOR_SJ"])
        sheet.append(["Maria Silva", "MARI", "Meia", "G1", 60,
                      30, 31, 32, 32, 25, "S/D", 27, 27])
        sheet.append(["MÉDIA", None, None, None, None,
                      30, 31, 32, 32, 25, 26, 27, 27])
        model = workbook.create_sheet("EM BRANCO")
        model.append(["NOME", "CMJ1"])
        buffer = io.BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()

    def test_extracts_dated_sheets_and_matches_registered_athlete(self):
        athletes = [{
            "id_atleta": 4, "nome": "Maria Silva", "apelido": "Mari",
            "nome_alternativo": None,
        }]
        result = extract_jump_workbook(
            self.workbook_bytes(), "saltos.xlsx", athletes
        )
        self.assertEqual(result["abas_ignoradas"], ["EM BRANCO"])
        self.assertEqual(len(result["linhas"]), 1)
        row = result["linhas"][0]
        self.assertEqual(row["athlete_id"], 4)
        self.assertEqual(row["data_coleta"], date(2026, 6, 22))
        self.assertEqual(row["cmj3"], 32.0)
        self.assertEqual(row["sj1"], 25.0)
        self.assertIsNone(row["sj2"])
        self.assertEqual(row["sj3"], 27.0)

    def test_manual_selection_resolves_only_the_matching_error(self):
        result = extract_jump_workbook(self.workbook_bytes(), "saltos.xlsx", [])
        row = result["linhas"][0]
        self.assertIsNone(row["athlete_id"])
        row["athlete_id"] = 9
        row["jogador"] = "Mari — ID 9"
        row["erros"] = []
        prepared = prepare_jump_rows([row])[0]
        self.assertEqual(prepared.athlete_id, 9)
        self.assertFalse(prepared.errors)


if __name__ == "__main__":
    unittest.main()
