import unittest
from datetime import date
from unittest.mock import MagicMock

from backend.mac_api.modules.athletes.athlete_service import (
    create_athlete,
    deactivate_athlete,
    reactivate_athlete,
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

    def test_deactivate_preserves_athlete_with_measurements(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (7,)
        deactivate_athlete(7, connection_factory=connection_factory(cursor))
        self.assertEqual(cursor.execute.call_count, 1)
        query, parameters = cursor.execute.call_args.args
        self.assertIn("SET status = 'inativo'", query)
        self.assertNotIn("DELETE", query)
        self.assertNotIn("medida_valor", query)
        self.assertEqual(parameters, (7,))

    def test_deactivate_missing_athlete(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        with self.assertRaisesRegex(ValueError, "não encontrado"):
            deactivate_athlete(7, connection_factory=connection_factory(cursor))

    def test_reactivate_preserves_identity_and_measurements(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (7,)
        reactivate_athlete(7, connection_factory=connection_factory(cursor))
        self.assertEqual(cursor.execute.call_count, 1)
        query, parameters = cursor.execute.call_args.args
        self.assertIn("SET status = 'ativo'", query)
        self.assertNotIn('DELETE', query)
        self.assertNotIn('INSERT', query)
        self.assertNotIn('medida_valor', query)
        self.assertEqual(parameters, (7,))

    def test_reactivate_missing_athlete(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        with self.assertRaisesRegex(ValueError, 'não encontrado'):
            reactivate_athlete(7, connection_factory=connection_factory(cursor))
