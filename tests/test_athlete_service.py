import unittest
from datetime import date
from unittest.mock import MagicMock

from athlete_service import (
    AthleteInUseError,
    create_athlete,
    delete_athlete,
    update_athlete,
)


def connection_factory(cursor: MagicMock):
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    context = MagicMock()
    context.__enter__.return_value = connection
    context.__exit__.return_value = False
    return lambda: context


class AthleteServiceTests(unittest.TestCase):
    def test_create_requires_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "Nome"):
            create_athlete(name="   ", connection_factory=MagicMock())

    def test_create_normalizes_optional_fields(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (42,)

        athlete_id = create_athlete(
            name="  Jogador Teste  ",
            nickname=" ",
            position=" Meia ",
            group="",
            birth_date=date(2000, 1, 2),
            connection_factory=connection_factory(cursor),
        )

        self.assertEqual(athlete_id, 42)
        parameters = cursor.execute.call_args.args[1]
        self.assertEqual(
            parameters,
            ("Jogador Teste", None, "Meia", None, date(2000, 1, 2)),
        )
        self.assertNotIn("nome_alternativo", cursor.execute.call_args.args[0])

    def test_update_preserves_alternative_name(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (7,)

        update_athlete(
            7,
            name="Nome",
            nickname="Apelido",
            connection_factory=connection_factory(cursor),
        )

        query = cursor.execute.call_args.args[0]
        self.assertNotIn("nome_alternativo", query)
        self.assertIn("WHERE id_atleta = %s", query)

    def test_delete_rejects_athlete_with_measurements(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (3,)

        with self.assertRaises(AthleteInUseError):
            delete_athlete(7, connection_factory=connection_factory(cursor))

        self.assertEqual(cursor.execute.call_count, 1)
        self.assertNotIn("DELETE", cursor.execute.call_args.args[0])

    def test_delete_unreferenced_athlete(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.side_effect = [(0,), (7,)]

        delete_athlete(7, connection_factory=connection_factory(cursor))

        self.assertEqual(cursor.execute.call_count, 2)
        self.assertIn("DELETE FROM public.atleta", cursor.execute.call_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
