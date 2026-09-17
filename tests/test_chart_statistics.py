from datetime import date
import unittest

from chart_statistics import daily_statistics


class DailyStatisticsTests(unittest.TestCase):
    def test_calculates_mean_and_population_deviation_for_each_date(self) -> None:
        records = [
            {"data_coleta": date(2026, 8, 2), "value": 10.0},
            {"data_coleta": date(2026, 8, 1), "value": 10.0},
            {"data_coleta": date(2026, 8, 1), "value": 14.0},
            {"data_coleta": date(2026, 8, 2), "value": 20.0},
        ]

        dates, means, deviations = daily_statistics(
            records, lambda record: float(record["value"])
        )

        self.assertEqual(dates, [date(2026, 8, 1), date(2026, 8, 2)])
        self.assertEqual(means, [12.0, 15.0])
        self.assertEqual(deviations, [2.0, 5.0])

    def test_single_valid_measurement_has_zero_deviation(self) -> None:
        records = [{"data_coleta": date(2026, 8, 1), "value": 7.5}]

        _, means, deviations = daily_statistics(
            records, lambda record: float(record["value"])
        )

        self.assertEqual(means, [7.5])
        self.assertEqual(deviations, [0.0])

    def test_ignores_invalid_values_without_misaligning_dates(self) -> None:
        records = [
            {"data_coleta": date(2026, 8, 1), "value": None},
            {"data_coleta": date(2026, 8, 2), "value": -1.0},
            {"data_coleta": date(2026, 8, 2), "value": 0.0},
            {"data_coleta": date(2026, 8, 3), "value": 9.0},
        ]

        dates, means, deviations = daily_statistics(
            records,
            lambda record: (
                float(record["value"])
                if record["value"] is not None and float(record["value"]) >= 0
                else None
            ),
        )

        self.assertEqual(dates, [date(2026, 8, 2), date(2026, 8, 3)])
        self.assertEqual(means, [0.0, 9.0])
        self.assertEqual(deviations, [0.0, 0.0])


if __name__ == "__main__":
    unittest.main()
