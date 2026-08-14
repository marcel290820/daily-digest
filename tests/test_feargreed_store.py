import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone

from daily_digest import store
from daily_digest.feargreed import (
    CRYPTO,
    STOCKS,
    ZONE_EXTREME_FEAR,
    ZONE_EXTREME_GREED,
    ZONE_NORMAL,
    Reading,
    alert_needed,
    zone,
)

BASE_TS = datetime(2026, 8, 14, tzinfo=timezone.utc)


def _reading(index: str, value: int, day: int = 0) -> Reading:
    return Reading(
        index=index,
        value=value,
        rating="Fear",
        ts=BASE_TS + timedelta(days=day),
    )


class Zones(unittest.TestCase):
    def test_bounds_are_inclusive(self) -> None:
        self.assertEqual(zone(10, 10, 90), ZONE_EXTREME_FEAR)
        self.assertEqual(zone(11, 10, 90), ZONE_NORMAL)
        self.assertEqual(zone(89, 10, 90), ZONE_NORMAL)
        self.assertEqual(zone(90, 10, 90), ZONE_EXTREME_GREED)

    def test_stock_and_crypto_thresholds_differ(self) -> None:
        self.assertEqual(zone(15, 20, 80), ZONE_EXTREME_FEAR)  # stocks
        self.assertEqual(zone(15, 10, 90), ZONE_NORMAL)  # crypto


class AlertNeeded(unittest.TestCase):
    def test_first_reading_alerts_only_when_extreme(self) -> None:
        self.assertTrue(alert_needed(None, _reading(CRYPTO, 5), 10, 90))
        self.assertFalse(alert_needed(None, _reading(CRYPTO, 50), 10, 90))

    def test_entering_extreme_alerts(self) -> None:
        previous = _reading(CRYPTO, 40)
        self.assertTrue(alert_needed(previous, _reading(CRYPTO, 9, 1), 10, 90))

    def test_staying_extreme_is_silent(self) -> None:
        previous = _reading(CRYPTO, 9)
        self.assertFalse(alert_needed(previous, _reading(CRYPTO, 4, 1), 10, 90))

    def test_flipping_to_the_other_extreme_alerts(self) -> None:
        previous = _reading(CRYPTO, 5)
        self.assertTrue(alert_needed(previous, _reading(CRYPTO, 95, 1), 10, 90))

    def test_leaving_extreme_is_silent(self) -> None:
        previous = _reading(CRYPTO, 5)
        self.assertFalse(alert_needed(previous, _reading(CRYPTO, 50, 1), 10, 90))


class Store(unittest.TestCase):
    def test_insert_is_idempotent(self) -> None:
        with closing(store.connect(":memory:")) as conn:
            reading = _reading(STOCKS, 42)
            self.assertEqual(store.record(conn, [reading]), 1)
            self.assertEqual(store.record(conn, [reading]), 0)

    def test_revised_value_at_a_known_timestamp_wins(self) -> None:
        with closing(store.connect(":memory:")) as conn:
            store.record(conn, [_reading(CRYPTO, 12)])
            revised = Reading(index=CRYPTO, value=8, rating="Extreme Fear", ts=BASE_TS)
            self.assertEqual(store.record(conn, [revised]), 1)
            newest = store.latest(conn, CRYPTO)
            self.assertEqual(newest.value, 8)
            self.assertEqual(newest.rating, "Extreme Fear")

    def test_a_revision_does_not_re_alert_on_the_next_check(self) -> None:
        """The source revising today's value must not replay the crossing."""
        with closing(store.connect(":memory:")) as conn:
            store.record(conn, [_reading(CRYPTO, 12)])
            revised = Reading(index=CRYPTO, value=8, rating="Extreme Fear", ts=BASE_TS)
            self.assertTrue(alert_needed(store.latest(conn, CRYPTO), revised, 10, 90))
            store.record(conn, [revised])
            self.assertFalse(alert_needed(store.latest(conn, CRYPTO), revised, 10, 90))

    def test_latest_returns_newest_per_index(self) -> None:
        with closing(store.connect(":memory:")) as conn:
            store.record(
                conn,
                [
                    _reading(STOCKS, 42, 0),
                    _reading(STOCKS, 44, 2),
                    _reading(STOCKS, 43, 1),
                    _reading(CRYPTO, 10, 5),
                ],
            )
            newest = store.latest(conn, STOCKS)
            self.assertIsNotNone(newest)
            self.assertEqual(newest.value, 44)
            self.assertEqual(newest.ts, BASE_TS + timedelta(days=2))
            self.assertEqual(store.latest(conn, CRYPTO).value, 10)

    def test_latest_on_empty_index_is_none(self) -> None:
        with closing(store.connect(":memory:")) as conn:
            self.assertIsNone(store.latest(conn, STOCKS))

    def test_record_of_nothing_is_a_noop(self) -> None:
        with closing(store.connect(":memory:")) as conn:
            self.assertEqual(store.record(conn, []), 0)


class CheckerSequence(unittest.TestCase):
    """The hourly checker loop: read previous, decide, then record."""

    def _run(self, values: list[int], low: int, high: int) -> list[int]:
        fired: list[int] = []
        with closing(store.connect(":memory:")) as conn:
            for day, value in enumerate(values):
                current = _reading(CRYPTO, value, day)
                previous = store.latest(conn, CRYPTO)
                if alert_needed(previous, current, low, high):
                    fired.append(value)
                store.record(conn, [current])
        return fired

    def test_alerts_once_per_entry_into_an_extreme_zone(self) -> None:
        values = [50, 8, 6, 7, 40, 5, 95]
        self.assertEqual(self._run(values, 10, 90), [8, 5, 95])

    def test_normal_readings_never_alert(self) -> None:
        self.assertEqual(self._run([50, 30, 70, 21, 79], 20, 80), [])


if __name__ == "__main__":
    unittest.main()
