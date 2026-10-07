import contextlib
import io
import unittest
from unittest import mock

import httpx

from daily_digest import __main__ as cli
from daily_digest.system import render_system, samples, usage


class SystemMetrics(unittest.TestCase):
    def test_missing_buckets_are_excluded_and_coverage_is_visible(self) -> None:
        payload = {
            "labels": ["time", "user", "system", "idle"],
            "data": [[300, 20, 5, 75], [600, None, None, None], [900, 40, 10, 50]],
        }
        avg, peak, hours = usage("system.cpu", payload)
        self.assertEqual((avg, peak), (37.5, 50.0))
        self.assertAlmostEqual(hours, 10 / 60)
        self.assertEqual(len(samples(payload)), 2)

    def test_ram_excludes_cached_memory(self) -> None:
        ram = {
            "labels": ["time", "used", "free", "cached", "buffers"],
            "data": [[300, 25, 25, 40, 10], [600, 50, 10, 30, 10]],
        }
        self.assertEqual(usage("system.ram", ram)[:2], (37.5, 50.0))

    def test_empty_malformed_and_non_finite_history_is_rejected(self) -> None:
        for data in ([], [[1, None]], [[1]], [[1, float("nan")]]):
            with self.subTest(data=data), self.assertRaises(ValueError):
                samples({"labels": ["time", "used"], "data": data})


class SystemCommand(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_dispatch_does_not_send(self) -> None:
        sender = mock.AsyncMock()
        output = io.StringIO()
        with (
            mock.patch(
                "daily_digest.system.render_system",
                mock.AsyncMock(return_value="report"),
            ),
            mock.patch("daily_digest.telegram.send_markdown", sender),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(await cli._dispatch("system", True, False), 0)
        self.assertEqual(output.getvalue().strip(), "report")
        sender.assert_not_awaited()

    async def test_send_failure_propagates_for_systemd(self) -> None:
        with (
            mock.patch(
                "daily_digest.system.render_system",
                mock.AsyncMock(return_value="report"),
            ),
            mock.patch(
                "daily_digest.telegram.send_markdown",
                mock.AsyncMock(side_effect=RuntimeError("down")),
            ),
            self.assertRaises(RuntimeError),
        ):
            await cli._dispatch("system", False, False)

    async def test_monitoring_outage_is_reported_as_unavailable(self) -> None:
        states = "\n\n".join(
            f"Id={name}.service\nActiveState=active\nSubState=running"
            for name in ("ssh", "cron")
        )
        with (
            mock.patch(
                "daily_digest.system._query",
                mock.AsyncMock(side_effect=httpx.ConnectError("offline")),
            ),
            mock.patch(
                "daily_digest.system._command", mock.AsyncMock(side_effect=[states, ""])
            ),
            mock.patch("daily_digest.system.Path.read_text", return_value="3600 0"),
        ):
            report = await render_system()
        self.assertIn("CPU history unavailable", report)
        self.assertIn("Netdata alerts unavailable", report)
        self.assertIn("CPU   n/a", report)
        self.assertNotIn("All good", report)

    async def test_inactive_and_failed_services_are_named(self) -> None:
        with (
            mock.patch(
                "daily_digest.system._query",
                mock.AsyncMock(side_effect=httpx.ConnectError("offline")),
            ),
            mock.patch(
                "daily_digest.system._command",
                mock.AsyncMock(
                    side_effect=[
                        "Id=netdata.service\nActiveState=inactive\nSubState=dead",
                        "daily-digest@news.service loaded failed failed News",
                    ]
                ),
            ),
            mock.patch("daily_digest.system.Path.read_text", return_value="3600 0"),
        ):
            report = await render_system()
        self.assertIn(r"netdata\.service inactive", report)
        self.assertIn("Service check incomplete", report)
        self.assertIn(r"daily\-digest@news\.service failed", report)


class SystemAlerts(unittest.IsolatedAsyncioTestCase):
    async def _report(
        self, alarms: object, cpu: object = None, failed: str | None = None
    ) -> str:
        if cpu is None:
            cpu = {"labels": ["time", "user", "idle"], "data": [[300, 5, 95]]}
        command: object = httpx.ConnectError("offline")
        if failed is not None:
            command = [httpx.ConnectError("offline"), failed]
        with (
            mock.patch(
                "daily_digest.system._query",
                mock.AsyncMock(side_effect=[cpu, cpu, alarms]),
            ),
            mock.patch(
                "daily_digest.system._command", mock.AsyncMock(side_effect=command)
            ),
        ):
            return await render_system()

    async def test_disabled_null_or_malformed_alerts_are_issues(self) -> None:
        for alarms in ({"status": False, "alarms": {}}, None, {"status": True}):
            with self.subTest(alarms=alarms):
                report = await self._report(alarms)
                self.assertIn("Netdata alerts invalid or disabled", report)

    async def test_active_alert_is_named(self) -> None:
        alarms = {
            "status": True,
            "alarms": {"x": {"status": "WARNING", "name": "disk_space"}},
        }
        self.assertIn(r"Warning: disk\_space", await self._report(alarms))

    async def test_null_history_is_invalid(self) -> None:
        report = await self._report({"status": True, "alarms": {}}, cpu=[None])
        self.assertIn("CPU history invalid", report)

    async def test_many_issues_fit_one_message(self) -> None:
        failed = "\n".join(
            f"unit{i}.service loaded failed failed x" for i in range(200)
        )
        report = await self._report({"status": True, "alarms": {}}, failed=failed)
        self.assertLess(len(report), 4096)
        self.assertEqual(report.count("```"), 2)
        self.assertIn("more", report)
