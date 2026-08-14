import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from daily_digest.feargreed import CRYPTO, STOCKS
from daily_digest.sources.feargreed import (
    CNN_HEADERS,
    parse_cnn,
    parse_cnn_history,
    parse_crypto,
    parse_crypto_history,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class ParseCnn(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = _fixture("cnn_graphdata.json")

    def test_current_reading(self) -> None:
        reading = parse_cnn(self.payload)
        self.assertEqual(reading.index, STOCKS)
        self.assertEqual(reading.value, 67)  # 66.74 rounded at the boundary
        self.assertEqual(reading.rating, "Greed")  # CNN sends it lowercase
        self.assertEqual(
            reading.ts, datetime(2026, 8, 14, 10, 16, 1, tzinfo=timezone.utc)
        )
        self.assertEqual(reading.previous_close, 66)
        self.assertEqual(reading.previous_week, 64)
        self.assertEqual(reading.previous_month, 41)

    def test_history_parses_epoch_millis(self) -> None:
        readings = parse_cnn_history(self.payload)
        self.assertEqual(len(readings), 3)
        first = readings[0]
        self.assertEqual(first.index, STOCKS)
        self.assertEqual(first.value, 63)
        self.assertEqual(first.ts, datetime(2025, 8, 14, tzinfo=timezone.utc))
        self.assertIsNone(first.previous_close)

    def test_out_of_range_value_is_rejected(self) -> None:
        self.payload["fear_and_greed"]["score"] = 140.0
        with self.assertRaises(ValueError):
            parse_cnn(self.payload)

    def test_missing_key_raises(self) -> None:
        del self.payload["fear_and_greed"]
        with self.assertRaises(KeyError):
            parse_cnn(self.payload)

    def test_request_carries_both_headers_cnn_demands(self) -> None:
        """Dropping either one turns every fetch into a 418."""
        self.assertIn("Mozilla/5.0", CNN_HEADERS["User-Agent"])
        self.assertIn("cnn.com", CNN_HEADERS["Referer"])


class ParseCrypto(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = _fixture("crypto_fng.json")

    def test_current_reading(self) -> None:
        reading = parse_crypto(self.payload)
        self.assertEqual(reading.index, CRYPTO)
        self.assertEqual(reading.value, 29)
        self.assertEqual(reading.rating, "Fear")
        self.assertEqual(
            reading.ts, datetime.fromtimestamp(1786665600, tz=timezone.utc)
        )
        self.assertEqual(reading.previous_close, 29)
        self.assertEqual(reading.previous_week, 29)
        self.assertEqual(reading.previous_month, 25)

    def test_comparisons_come_from_1_7_and_30_days_back(self) -> None:
        """Entries are daily and newest first, so offset N is N days back.

        The live fixture happens to hold equal values around those offsets, so
        this stamps each entry with its own index to pin the arithmetic.
        """
        for offset, entry in enumerate(self.payload["data"]):
            entry["value"] = str(offset)
        reading = parse_crypto(self.payload)
        self.assertEqual(reading.value, 0)
        self.assertEqual(reading.previous_close, 1)
        self.assertEqual(reading.previous_week, 7)
        self.assertEqual(reading.previous_month, 30)

    def test_short_response_drops_missing_comparisons(self) -> None:
        self.payload["data"] = self.payload["data"][:3]
        reading = parse_crypto(self.payload)
        self.assertEqual(reading.previous_close, 29)
        self.assertIsNone(reading.previous_week)
        self.assertIsNone(reading.previous_month)

    def test_empty_response_raises(self) -> None:
        self.payload["data"] = []
        with self.assertRaises(ValueError):
            parse_crypto(self.payload)

    def test_history_is_one_reading_per_entry(self) -> None:
        readings = parse_crypto_history(self.payload)
        self.assertEqual(len(readings), 31)
        self.assertEqual(readings[-1].value, 25)
        self.assertEqual(readings[-1].rating, "Extreme Fear")
        self.assertEqual(
            readings[-1].ts, datetime.fromtimestamp(1784073600, tz=timezone.utc)
        )


if __name__ == "__main__":
    unittest.main()
