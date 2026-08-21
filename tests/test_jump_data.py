from datetime import date, timedelta
import unittest

from jump_data import build_jump_comparison, metric_summary


def record(
    athlete: str,
    position: str,
    cmj: float | None,
    sj: float | None,
    day: int = 0,
) -> dict[str, object]:
    return {
        "atleta": athlete,
        "posicao": position,
        "data_coleta": date(2026, 8, 1) + timedelta(days=day),
        "maior_cmj": cmj,
        "maior_sj": sj,
    }


class JumpComparisonTests(unittest.TestCase):
    def test_classifies_above_average_and_below(self) -> None:
        records = [
            record("Baixo", "Lateral", 10, 10),
            record("Médio", "Lateral", 20, 20),
            record("Alto", "Lateral", 30, 30),
        ]

        rows = build_jump_comparison(records, records)
        analyses = {row["athlete"]: row["analysis"] for row in rows}

        self.assertEqual([row["athlete"] for row in rows], ["Alto", "Médio", "Baixo"])
        self.assertIn("Acima da média", analyses["Alto"])
        self.assertIn("Na média", analyses["Médio"])
        self.assertIn("Abaixo da média", analyses["Baixo"])

    def test_each_athlete_has_equal_weight_in_reference(self) -> None:
        records = [
            *[record("A", "Volante", 10, 10, day) for day in range(8)],
            record("B", "Volante", 20, 20),
            record("C", "Volante", 30, 30),
        ]

        rows = build_jump_comparison(records, records)
        middle = next(row for row in rows if row["athlete"] == "B")

        self.assertAlmostEqual(middle["analysis_score"], 0.0)
        self.assertIn("Na média", middle["analysis"])

    def test_uses_the_only_metric_with_a_valid_reference(self) -> None:
        records = [
            record("A", "Goleiro", 10, None),
            record("B", "Goleiro", 20, None),
            record("C", "Goleiro", 30, None),
        ]

        rows = build_jump_comparison(records, records)
        top = next(row for row in rows if row["athlete"] == "C")

        self.assertIsNotNone(top["analysis_score"])
        self.assertIn("Acima da média", top["analysis"])

    def test_reports_insufficient_data_for_single_or_constant_group(self) -> None:
        records = [
            record("Único", "Atacante", 30, 25),
            record("A", "Zagueiro", 20, 15),
            record("B", "Zagueiro", 20, 15),
        ]

        rows = build_jump_comparison(records, records)

        self.assertTrue(all("Dados insuficientes" in row["analysis"] for row in rows))

    def test_ignores_null_zero_and_negative_values(self) -> None:
        records = [
            record("A", "Lateral", None, None),
            record("A", "Lateral", 0, -2),
            record("A", "Lateral", 24, 18),
        ]

        self.assertEqual(metric_summary(records, "cmj"), (24.0, 0.0))
        self.assertEqual(metric_summary(records, "sj"), (18.0, 0.0))

    def test_display_records_control_visible_rows(self) -> None:
        references = [
            record("A", "Lateral", 10, 10),
            record("B", "Lateral", 20, 20),
            record("C", "Lateral", 30, 30),
        ]

        rows = build_jump_comparison([references[1]], references)

        self.assertEqual([row["athlete"] for row in rows], ["B"])


if __name__ == "__main__":
    unittest.main()
