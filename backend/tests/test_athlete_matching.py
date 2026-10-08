import unittest

from backend.mac_api.modules.athletes.athlete_matching import (
    athlete_selection_label,
    matching_athlete_ids,
    unique_matching_athlete_id,
)


class AthleteMatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.athletes = [
            {
                "id_atleta": 4,
                "nome": "Felipe Cruz",
                "apelido": "Cruz",
                "nome_alternativo": "F. Cruz, Felipe",
            },
            {
                "id_atleta": 8,
                "nome": "Felipe Silva",
                "apelido": "Silva",
                "nome_alternativo": "Felipe",
            },
        ]

    def test_matches_name_nickname_and_alternative_after_normalization(self) -> None:
        for value in ("felipe cruz", "CRÚZ", "f. cruz"):
            with self.subTest(value=value):
                self.assertEqual(
                    unique_matching_athlete_id(value, self.athletes), 4
                )

    def test_returns_none_for_unknown_or_ambiguous_name(self) -> None:
        self.assertIsNone(unique_matching_athlete_id("ninguém", self.athletes))
        self.assertEqual(matching_athlete_ids("Felipe", self.athletes), [4, 8])
        self.assertIsNone(unique_matching_athlete_id("Felipe", self.athletes))

    def test_selection_label_contains_database_id(self) -> None:
        self.assertEqual(
            athlete_selection_label(self.athletes[0]), "Cruz — ID 4"
        )


if __name__ == "__main__":
    unittest.main()
