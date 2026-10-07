import unittest
from datetime import date

from daily_digest.format import render_life


class RenderLifeTest(unittest.TestCase):
    def test_halfway(self) -> None:
        line = render_life(date(2000, 1, 1), date(2040, 1, 1))
        self.assertIn("▓▓▓▓▓░░░░░ 50\\.0% of 80 years lived", line)
        self.assertIn("14,610 days left", line)

    def test_past_end_clamps(self) -> None:
        line = render_life(date(1900, 1, 1), date(2000, 1, 1))
        self.assertIn("▓" * 10, line)
        self.assertIn(" 0 days left", line)

    def test_leap_day_birth_in_common_end_year(self) -> None:
        line = render_life(date(2020, 2, 29), date(2060, 1, 1))
        self.assertIn("of 80 years lived", line)

    def test_future_birth_rejected(self) -> None:
        with self.assertRaises(ValueError):
            render_life(date(2050, 1, 1), date(2026, 10, 8))


if __name__ == "__main__":
    unittest.main()
