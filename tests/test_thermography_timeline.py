import unittest
from datetime import date

from thermography_timeline import valid_timeline_selection


class ThermographyTimelineTests(unittest.TestCase):
    def test_selection_started_by_t0_only_accepts_later_ti(self) -> None:
        t0 = (date(2026, 10, 5), 2)
        self.assertTrue(
            valid_timeline_selection((date(2026, 10, 6), 3), t0, "ti")
        )
        self.assertFalse(
            valid_timeline_selection((date(2026, 10, 4), 4), t0, "ti")
        )

    def test_selection_started_by_ti_only_accepts_earlier_t0(self) -> None:
        ti = (date(2026, 10, 5), 3)
        self.assertTrue(
            valid_timeline_selection((date(2026, 10, 4), 4), ti, "t0")
        )
        self.assertFalse(
            valid_timeline_selection((date(2026, 10, 6), 1), ti, "t0")
        )

    def test_same_date_is_ordered_by_session_sequence(self) -> None:
        ti = (date(2026, 10, 5), 3)
        self.assertTrue(
            valid_timeline_selection((date(2026, 10, 5), 2), ti, "t0")
        )
        self.assertFalse(
            valid_timeline_selection((date(2026, 10, 5), 4), ti, "t0")
        )


if __name__ == "__main__":
    unittest.main()
