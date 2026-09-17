from datetime import date
import unittest

from gps_data import opponents_by_date


class GpsOpponentTests(unittest.TestCase):
    def test_groups_unique_opponents_by_date(self) -> None:
        first_date = date(2026, 9, 1)
        second_date = date(2026, 9, 2)
        records = [
            {"data_coleta": first_date, "equipe": "MAC", "adversario": "Luminense"},
            {"data_coleta": first_date, "equipe": "MAC", "adversario": "Luminense"},
            {"data_coleta": first_date, "equipe": "MAC", "adversario": "Imperatriz"},
            {"data_coleta": second_date, "adversario": None},
            {"data_coleta": second_date, "adversario": "  "},
        ]

        opponents = opponents_by_date(records)

        self.assertEqual(opponents[first_date], "Imperatriz / Luminense")
        self.assertNotIn(second_date, opponents)

    def test_uses_team_when_opponent_is_mac(self) -> None:
        collection_date = date(2026, 9, 3)
        records = [
            {
                "data_coleta": collection_date,
                "equipe": "Moto Club",
                "adversario": "  mac  ",
            }
        ]

        opponents = opponents_by_date(records)

        self.assertEqual(opponents[collection_date], "Moto Club")

    def test_extracts_opponent_from_team_when_opponent_is_null(self) -> None:
        collection_date = date(2026, 9, 4)
        records = [
            {
                "data_coleta": collection_date,
                "equipe": "Imperatriz X MAC",
                "adversario": None,
            }
        ]

        opponents = opponents_by_date(records)

        self.assertEqual(opponents[collection_date], "Imperatriz")

    def test_ignores_team_without_match_format_when_opponent_is_null(self) -> None:
        collection_date = date(2026, 9, 5)
        records = [
            {
                "data_coleta": collection_date,
                "equipe": "Imperatriz",
                "adversario": None,
            }
        ]

        self.assertNotIn(collection_date, opponents_by_date(records))


if __name__ == "__main__":
    unittest.main()
