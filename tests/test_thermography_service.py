import unittest
from datetime import date
from unittest.mock import MagicMock

from thermography_service import (
    DuplicateThermographyError,
    IMAGE_MEASURES,
    LegacyThermographyRecord,
    image_measurements,
    save_image_thermography,
    save_legacy_thermography,
)


def connection_factory(cursor: MagicMock):
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    context = MagicMock()
    context.__enter__.return_value = connection
    context.__exit__.return_value = False
    return lambda: context


class ThermographyServiceTests(unittest.TestCase):
    def test_image_measurements_calculates_sums(self) -> None:
        measurements = image_measurements(
            mass=72.5,
            pain_score=3,
            front_right=10,
            front_left=20,
            back_right=30,
            back_left=40,
            observations=" Sem queixas ",
        )

        self.assertEqual(measurements["SOMA_FRENTE"], 30)
        self.assertEqual(measurements["SOMA_VERSO"], 70)
        self.assertEqual(measurements["OBSERVACOES"], "Sem queixas")

    def test_image_measurements_rejects_invalid_eva(self) -> None:
        with self.assertRaisesRegex(ValueError, "EVA"):
            image_measurements(
                mass=72,
                pain_score=11,
                front_right=1,
                front_left=1,
                back_right=1,
                back_left=1,
            )

    def test_saves_all_image_measures_in_one_collection(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.side_effect = [(7,), (0,)]
        cursor.fetchall.return_value = [
            (index, name) for index, name in enumerate(sorted(IMAGE_MEASURES), start=1)
        ]

        inserted = save_image_thermography(
            athlete_id=7,
            collected_at=date(2026, 9, 18),
            mass=72,
            pain_score=2,
            front_right=10,
            front_left=20,
            back_right=30,
            back_left=40,
            observations="Ok",
            connection_factory=connection_factory(cursor),
        )

        self.assertEqual(inserted, 9)
        values = cursor.executemany.call_args.args[1]
        self.assertEqual(len(values), 9)
        self.assertTrue(all(value[0] == 7 for value in values))
        self.assertTrue(all(value[1] is None for value in values))
        self.assertEqual(len({value[5] for value in values}), 1)

    def test_rejects_existing_collection(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.side_effect = [(7,), (3,)]
        cursor.fetchall.return_value = [
            (index, name) for index, name in enumerate(sorted(IMAGE_MEASURES), start=1)
        ]

        with self.assertRaises(DuplicateThermographyError):
            save_image_thermography(
                athlete_id=7,
                collected_at=date(2026, 9, 18),
                mass=72,
                pain_score=2,
                front_right=10,
                front_left=20,
                back_right=30,
                back_left=40,
                connection_factory=connection_factory(cursor),
            )

        cursor.executemany.assert_not_called()

    def test_legacy_batch_rejects_repeated_athlete_and_date(self) -> None:
        record = LegacyThermographyRecord(
            athlete_id=7,
            collected_at=date(2026, 9, 18),
            mass=72,
            pain_score=2,
            front=30,
            back=70,
        )

        with self.assertRaisesRegex(ValueError, "mesmo jogador e data"):
            save_legacy_thermography(
                [record, record], connection_factory=MagicMock()
            )


if __name__ == "__main__":
    unittest.main()
