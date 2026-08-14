import unittest
from datetime import datetime, timezone

from daily_digest.feargreed import CRYPTO, STOCKS, Reading
from daily_digest.format import render_feargreed, render_feargreed_alert

TS = datetime(2026, 8, 14, tzinfo=timezone.utc)

STOCKS_READING = Reading(
    index=STOCKS,
    value=67,
    rating="Greed",
    ts=TS,
    previous_close=66,
    previous_week=64,
    previous_month=41,
)
CRYPTO_READING = Reading(
    index=CRYPTO,
    value=29,
    rating="Fear",
    ts=TS,
    previous_close=29,
    previous_week=29,
    previous_month=25,
)


class RenderSection(unittest.TestCase):
    def test_both_indices(self) -> None:
        self.assertEqual(
            render_feargreed([STOCKS_READING, CRYPTO_READING]),
            "*📊 Fear & Greed*\n"
            "*Stocks* 67 Greed \\| prev 66 \\| 1w 64 \\| 1m 41\n"
            "*Crypto* 29 Fear \\| prev 29 \\| 1w 29 \\| 1m 25",
        )

    def test_missing_comparisons_are_dropped(self) -> None:
        bare = Reading(index=CRYPTO, value=5, rating="Extreme Fear", ts=TS)
        self.assertEqual(
            render_feargreed([bare]),
            "*📊 Fear & Greed*\n*Crypto* 5 Extreme Fear",
        )

    def test_only_one_index_available(self) -> None:
        self.assertEqual(
            render_feargreed([STOCKS_READING]),
            "*📊 Fear & Greed*\n*Stocks* 67 Greed \\| prev 66 \\| 1w 64 \\| 1m 41",
        )


class RenderAlert(unittest.TestCase):
    def test_with_previous_reading(self) -> None:
        current = Reading(index=STOCKS, value=18, rating="Extreme Fear", ts=TS)
        previous = Reading(index=STOCKS, value=24, rating="Fear", ts=TS)
        self.assertEqual(
            render_feargreed_alert(current, previous),
            "*🚨 Stocks Fear & Greed*\n*18* Extreme Fear \\(was 24, Fear\\)",
        )

    def test_without_previous_reading(self) -> None:
        current = Reading(index=CRYPTO, value=94, rating="Extreme Greed", ts=TS)
        self.assertEqual(
            render_feargreed_alert(current, None),
            "*🚨 Crypto Fear & Greed*\n*94* Extreme Greed \\(first reading\\)",
        )


if __name__ == "__main__":
    unittest.main()
