from contextlib import contextmanager
from datetime import datetime
import unittest
from unittest.mock import patch

from gps_import_service import (
    GpsFileMetadata,
    GpsMeasurement,
    PreparedGpsDocument,
    import_gps_documents,
    normalize_position,
    parse_gps_filename,
    parse_metric_value,
    payload_signature,
    prepare_gps_documents,
    preview_gps_documents,
)


class FakeCursor:
    def __init__(self) -> None:
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None) -> None:
        self.executions.append((query, params))


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakeCursor()

    def cursor(self):
        return self.cursor_instance


def connection_factory(connection: FakeConnection):
    @contextmanager
    def factory():
        yield connection

    return factory


def document(filename="01.02.2026_16_00h_MAC X LUMINENSE.pdf"):
    metadata = parse_gps_filename(filename)
    return PreparedGpsDocument(
        metadata=metadata,
        filename=filename,
        measurements=(
            GpsMeasurement("CAIO", "ATA", "Distance (km)", 5.2, "5,2", 1),
            GpsMeasurement("CAIO", "ATA", "Sprint Efforts", 3.0, "3", 1),
        ),
        errors=(),
    )


class GpsImportPreparationTests(unittest.TestCase):
    def test_parses_filename_with_local_timestamp_and_match(self) -> None:
        parsed = parse_gps_filename(
            "01.02.2026_16_00h_MAC X LUMINENSE.pdf"
        )

        self.assertEqual(parsed.collected_at, datetime(2026, 2, 1, 16, 0))
        self.assertEqual((parsed.team, parsed.opponent), ("MAC", "LUMINENSE"))

    def test_rejects_invalid_filename(self) -> None:
        with self.assertRaisesRegex(ValueError, "fora do padrão"):
            parse_gps_filename("relatorio.pdf")

    def test_accepts_comma_dot_and_negative_numbers(self) -> None:
        self.assertEqual(parse_metric_value("5,25"), (5.25, "5,25"))
        self.assertEqual(parse_metric_value("-3.4"), (-3.4, "-3.4"))
        with self.assertRaises(ValueError):
            parse_metric_value("1.234,5")

    def test_normalizes_position_abbreviations_and_punctuation(self) -> None:
        expected = {
            "CA": "Centroavante",
            "ext": "Extrema",
            "GOL": "Goleiro",
            "Ponta": "Ponta",
            "vol": "Volante",
            "mei": "Meia",
            "L.D.": "Lateral",
            "L E": "Lateral",
            "zag": "Zagueiro",
            "ata": "Atacante",
        }

        self.assertEqual(
            {value: normalize_position(value) for value in expected}, expected
        )
        with self.assertRaisesRegex(ValueError, "posição desconhecida"):
            normalize_position("indefinida")

    def test_prepares_edited_rows_and_ignores_source_column(self) -> None:
        prepared = prepare_gps_documents(
            [
                {
                    "arquivo": "01.02.2026_16_00h_MAC X LUMINENSE.pdf",
                    "linhas": [
                        {
                            "_arquivo": "ignorado.pdf",
                            "Nome": "CAIO, CAIO",
                            "Posição": "ATA",
                            "Distance (km)": "5,2",
                            "Sprint Efforts": "",
                        }
                    ],
                }
            ]
        )[0]

        self.assertEqual(prepared.errors, ())
        self.assertEqual(prepared.measurements[0].athlete, "CAIO")
        self.assertEqual(prepared.measurements[0].metric, "Distance (km)")
        self.assertEqual(prepared.measurements[0].value, 5.2)

    def test_editing_a_value_changes_validation_signature(self) -> None:
        original = [{"arquivo": "a.pdf", "linhas": [{"Métrica": "1,0"}]}]
        edited = [{"arquivo": "a.pdf", "linhas": [{"Métrica": "2,0"}]}]

        self.assertNotEqual(payload_signature(original), payload_signature(edited))


class GpsImportDatabaseTests(unittest.TestCase):
    def test_preview_reports_creations_and_duplicates_without_writes(self) -> None:
        connection = FakeConnection()
        with (
            patch(
                "gps_import_service._fetch_existing_athletes",
                return_value={"CAIO": (1, "ATA")},
            ),
            patch("gps_import_service._fetch_match", return_value=2),
            patch("gps_import_service._fetch_group", return_value=3),
            patch(
                "gps_import_service._fetch_metrics",
                return_value={"Distance (km)": 10},
            ),
            patch(
                "gps_import_service._fetch_duplicate_pairs",
                return_value={(1, 10)},
            ),
            patch("gps_import_service.execute_values") as batch_insert,
        ):
            preview = preview_gps_documents(
                [document()], connection_factory(connection)
            )[0]

        self.assertEqual(preview.duplicate_measurements, 1)
        self.assertEqual(preview.new_measurements, 1)
        self.assertEqual(preview.new_metrics, ("Sprint Efforts",))
        self.assertFalse(preview.new_match)
        batch_insert.assert_not_called()

    def test_import_locks_skips_duplicate_and_batches_new_value(self) -> None:
        connection = FakeConnection()
        with (
            patch("gps_import_service._get_or_create_group", return_value=(3, False)),
            patch("gps_import_service._get_or_create_match", return_value=(2, True)),
            patch("gps_import_service._get_or_create_athlete", return_value=(1, True)),
            patch(
                "gps_import_service._get_or_create_metric",
                side_effect=[(10, False), (11, True)],
            ),
            patch(
                "gps_import_service._fetch_duplicate_pairs",
                return_value={(1, 10)},
            ),
            patch("gps_import_service.execute_values") as batch_insert,
        ):
            result = import_gps_documents(
                [document()], connection_factory(connection)
            )[0]

        self.assertIn("pg_advisory_xact_lock", connection.cursor_instance.executions[0][0])
        self.assertEqual(result.inserted_measurements, 1)
        self.assertEqual(result.duplicate_measurements, 1)
        self.assertEqual(result.created_athletes, 1)
        batch_insert.assert_called_once()

    def test_failure_in_one_pdf_does_not_prevent_the_next(self) -> None:
        first_connection = FakeConnection()
        second_connection = FakeConnection()
        connections = iter([first_connection, second_connection])

        @contextmanager
        def factory():
            yield next(connections)

        with (
            patch(
                "gps_import_service._get_or_create_group",
                side_effect=[RuntimeError("falha simulada"), (3, False)],
            ),
            patch("gps_import_service._get_or_create_match", return_value=(2, False)),
            patch("gps_import_service._get_or_create_athlete", return_value=(1, False)),
            patch(
                "gps_import_service._get_or_create_metric",
                side_effect=[(10, False), (11, False)],
            ),
            patch("gps_import_service._fetch_duplicate_pairs", return_value=set()),
            patch("gps_import_service.execute_values"),
        ):
            results = import_gps_documents([document(), document()], factory)

        self.assertIn("falha simulada", results[0].error)
        self.assertIsNone(results[1].error)
        self.assertEqual(results[1].inserted_measurements, 2)


if __name__ == "__main__":
    unittest.main()
