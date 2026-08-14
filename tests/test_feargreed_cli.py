import io
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from unittest import mock

from daily_digest import __main__ as cli
from daily_digest.config import FEARGREED_EXTREMES
from daily_digest.feargreed import CRYPTO, STOCKS, Reading

TS = datetime(2026, 8, 14, tzinfo=timezone.utc)
STOCKS_READING = Reading(index=STOCKS, value=67, rating="Greed", ts=TS)
CRYPTO_READING = Reading(index=CRYPTO, value=29, rating="Fear", ts=TS)


def _stored(db: str) -> list[tuple]:
    """Rows in the database. The file itself exists as soon as it is opened."""
    with sqlite3.connect(db) as conn:
        return conn.execute("SELECT idx, value FROM readings").fetchall()


class Thresholds(unittest.TestCase):
    def test_every_index_has_a_band(self) -> None:
        self.assertEqual(set(FEARGREED_EXTREMES), {STOCKS, CRYPTO})

    def test_crypto_band_is_stricter_than_stocks(self) -> None:
        stocks_low, stocks_high = FEARGREED_EXTREMES[STOCKS]
        crypto_low, crypto_high = FEARGREED_EXTREMES[CRYPTO]
        self.assertLess(crypto_low, stocks_low)
        self.assertGreater(crypto_high, stocks_high)


class NewsDigest(unittest.IsolatedAsyncioTestCase):
    async def test_appends_the_section_without_touching_the_database(self) -> None:
        """The checker owns the database.

        If the digest recorded readings too, the next hourly check would
        compare against the digest's own row and miss the crossing.
        """
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "feargreed.db")
            out = io.StringIO()
            with (
                mock.patch.dict(os.environ, {"DIGEST_DB_PATH": db}),
                mock.patch.object(cli.rss, "top_entries", mock.AsyncMock(return_value=[])),
                mock.patch.object(
                    cli.feargreed_source, "fetch_stocks",
                    mock.AsyncMock(return_value=STOCKS_READING),
                ),
                mock.patch.object(
                    cli.feargreed_source, "fetch_crypto",
                    mock.AsyncMock(return_value=CRYPTO_READING),
                ),
                redirect_stdout(out),
            ):
                self.assertEqual(await cli._run("news", dry_run=True), 0)

            self.assertIn("Fear & Greed", out.getvalue())
            self.assertIn("*Stocks* 67 Greed", out.getvalue())
            self.assertFalse(os.path.exists(db))

    async def test_section_is_dropped_when_both_sources_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with (
                mock.patch.dict(
                    os.environ, {"DIGEST_DB_PATH": os.path.join(tmp, "feargreed.db")}
                ),
                mock.patch.object(cli.rss, "top_entries", mock.AsyncMock(return_value=[])),
                mock.patch.object(
                    cli.feargreed_source, "fetch_stocks",
                    mock.AsyncMock(side_effect=RuntimeError("cnn 418")),
                ),
                mock.patch.object(
                    cli.feargreed_source, "fetch_crypto",
                    mock.AsyncMock(side_effect=RuntimeError("api down")),
                ),
                redirect_stdout(out),
            ):
                self.assertEqual(await cli._run("news", dry_run=True), 0)

            self.assertNotIn("Fear & Greed", out.getvalue())


class Checker(unittest.IsolatedAsyncioTestCase):
    def _patches(self, db: str, stocks: Reading, crypto: Reading):
        return (
            mock.patch.dict(os.environ, {"DIGEST_DB_PATH": db}),
            mock.patch.object(
                cli.feargreed_source, "fetch_stocks", mock.AsyncMock(return_value=stocks)
            ),
            mock.patch.object(
                cli.feargreed_source, "fetch_crypto", mock.AsyncMock(return_value=crypto)
            ),
        )

    async def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "feargreed.db")
            env, stocks, crypto = self._patches(db, STOCKS_READING, CRYPTO_READING)
            with env, stocks, crypto, redirect_stdout(io.StringIO()):
                self.assertEqual(await cli._run_feargreed(dry_run=True), 0)
            self.assertEqual(_stored(db), [])

    async def test_a_failed_send_stores_nothing_so_the_alert_is_retried(self) -> None:
        """Alerts go out before readings are recorded.

        Recording first would swallow the crossing: the next run would see the
        same zone and stay silent about an alert that never arrived.
        """
        extreme = Reading(index=CRYPTO, value=5, rating="Extreme Fear", ts=TS)
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "feargreed.db")
            env, stocks, crypto = self._patches(db, STOCKS_READING, extreme)
            with (
                env,
                stocks,
                crypto,
                mock.patch(
                    "daily_digest.telegram.send_markdown",
                    mock.AsyncMock(side_effect=RuntimeError("telegram down")),
                ),
            ):
                with self.assertRaises(RuntimeError):
                    await cli._run_feargreed(dry_run=False)
            self.assertEqual(_stored(db), [])

    async def test_both_sources_failing_exits_non_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "feargreed.db")
            with (
                mock.patch.dict(os.environ, {"DIGEST_DB_PATH": db}),
                mock.patch.object(
                    cli.feargreed_source, "fetch_stocks",
                    mock.AsyncMock(side_effect=RuntimeError("cnn 418")),
                ),
                mock.patch.object(
                    cli.feargreed_source, "fetch_crypto",
                    mock.AsyncMock(side_effect=RuntimeError("api down")),
                ),
            ):
                self.assertEqual(await cli._run_feargreed(dry_run=False), 1)
            self.assertFalse(os.path.exists(db))

    async def test_alert_sent_once_per_crossing(self) -> None:
        extreme = Reading(index=CRYPTO, value=5, rating="Extreme Fear", ts=TS)
        sender = mock.AsyncMock()
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "feargreed.db")
            env, stocks, crypto = self._patches(db, STOCKS_READING, extreme)
            with env, stocks, crypto, mock.patch(
                "daily_digest.telegram.send_markdown", sender
            ):
                self.assertEqual(await cli._run_feargreed(dry_run=False), 0)
                self.assertEqual(sender.await_count, 1)
                self.assertIn("Crypto", sender.await_args.args[0])
                # Same reading an hour later: the index has not crossed again.
                self.assertEqual(await cli._run_feargreed(dry_run=False), 0)
                self.assertEqual(sender.await_count, 1)


if __name__ == "__main__":
    unittest.main()
