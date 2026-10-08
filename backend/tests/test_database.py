import unittest
from unittest.mock import MagicMock, patch

from backend.mac_api.core.database import database_write_connection


class DatabaseWriteConnectionTests(unittest.TestCase):
    def test_commits_and_closes_successful_pdf_transaction(self) -> None:
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = ("off",)

        with (
            patch("backend.mac_api.core.database.database_write_config", return_value={}),
            patch("backend.mac_api.core.database.psycopg2.connect", return_value=connection),
        ):
            with database_write_connection():
                pass

        connection.commit.assert_called_once()
        connection.rollback.assert_not_called()
        connection.close.assert_called_once()

    def test_rolls_back_and_closes_when_pdf_transaction_fails(self) -> None:
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = ("off",)

        with (
            patch("backend.mac_api.core.database.database_write_config", return_value={}),
            patch("backend.mac_api.core.database.psycopg2.connect", return_value=connection),
        ):
            with self.assertRaisesRegex(RuntimeError, "falha"):
                with database_write_connection():
                    raise RuntimeError("falha")

        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()
        connection.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
