"""Daily workstation report from local Netdata history and read-only OS state."""

import asyncio
import logging
import math
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import TypeVar
from zoneinfo import ZoneInfo

import httpx

from daily_digest.config import system_services
from daily_digest.format import escape

log = logging.getLogger("daily_digest.system")
_NETDATA = "http://127.0.0.1:19999/api/v1"
T = TypeVar("T")
_CHARTS = {"CPU": "system.cpu", "RAM": "system.ram"}
_HIGH_PCT = 90
_MIN_HISTORY_HOURS = 20
_MAX_ISSUES = 15


def samples(payload: dict) -> list[dict[str, float]]:
    """Exclude missing buckets; never turn missing telemetry into zero usage."""
    labels = payload["labels"]
    if not isinstance(labels, list) or not labels or labels[0] != "time":
        raise ValueError("Invalid Netdata labels")
    result = []
    for row in payload["data"]:
        if len(row) != len(labels):
            raise ValueError("Invalid Netdata row length")
        if any(value is None for value in row):
            continue
        if any(
            not isinstance(value, (int, float)) or not math.isfinite(value)
            for value in row
        ):
            raise ValueError("Invalid Netdata numeric value")
        result.append(dict(zip(labels, row)))
    if not result:
        raise ValueError("No historical samples available")
    return result


def usage(chart: str, payload: dict) -> tuple[float, float, float]:
    """Return (average %, peak %, hours of history) for system.cpu or system.ram."""
    rows = samples(payload)
    if chart == "system.cpu":
        values = [
            sum(v for k, v in row.items() if k not in ("time", "idle")) for row in rows
        ]
    else:
        values = [
            100
            * row["used"]
            / sum(row[k] for k in ("used", "free", "cached", "buffers"))
            for row in rows
        ]
    return mean(values), max(values), len(rows) * 5 / 60


async def _query(client: httpx.AsyncClient, path: str, params: dict | None = None):
    response = await client.get(f"{_NETDATA}/{path}", params=params)
    response.raise_for_status()
    return response.json()


async def _command(*args: str) -> str:
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)
    except BaseException:
        process.kill()
        await process.wait()
        raise
    if process.returncode:
        raise RuntimeError(stderr.decode().strip())
    return stdout.decode()


def _unwrap(result: T | BaseException, what: str, issues: list[str]) -> T | None:
    """Turn a gather() exception into a visible issue instead of a silent gap."""
    if isinstance(result, BaseException):
        if not isinstance(result, Exception):
            raise result
        log.warning("%s failed: %s", what, result)
        issues.append(f"{what} unavailable")
        return None
    return result


async def render_system() -> str:
    """Verdict first, issues by name, then a CPU/RAM/disk table.

    Healthy details (services, units, alerts) are omitted; only problems show.
    """
    # Fixed 5-minute buckets make gaps visible and avoid overstating short spikes.
    end = int(time.time()) // 300 * 300
    params = {
        "after": end - 86400,
        "before": end,
        "points": 288,
        "group": "average",
        "format": "json",
    }
    services = system_services()
    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        *histories, alarms = await asyncio.gather(
            *(
                _query(client, "data", {**params, "chart": chart})
                for chart in _CHARTS.values()
            ),
            _query(client, "alarms", {"all": "true"}),
            return_exceptions=True,
        )
    states, failed = await asyncio.gather(
        # With no names, `systemctl show` would describe the manager instead.
        _command(
            "systemctl",
            "show",
            *(f"{name}.service" for name in services),
            "--property=Id,ActiveState,SubState",
            "--no-pager",
        )
        if services
        else asyncio.sleep(0),
        _command(
            "systemctl",
            "list-units",
            "--failed",
            "--plain",
            "--no-legend",
            "--no-pager",
        ),
        return_exceptions=True,
    )

    issues: list[str] = []
    table: list[str] = []
    for (label, chart), result in zip(_CHARTS.items(), histories):
        if isinstance(result, BaseException):
            _unwrap(result, f"{label} history", issues)
            table.append(f"{label:<5} n/a")
            continue
        try:
            avg, peak, hours = usage(chart, result)
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
            log.warning("%s data invalid: %s", chart, exc)
            issues.append(f"{label} history invalid")
            table.append(f"{label:<5} n/a")
            continue
        if hours < _MIN_HISTORY_HOURS:
            issues.append(f"{label} history covers only {hours:.1f}h of 24h")
        if peak >= _HIGH_PCT:
            issues.append(f"{label} peaked at {peak:.0f}%")
        table.append(f"{label:<5}{avg:>3.0f}% avg  {peak:>3.0f}% peak")

    disk = shutil.disk_usage("/")
    disk_used = 100 * disk.used / disk.total
    inodes = os.statvfs("/")
    inodes_used = 100 * (1 - inodes.f_favail / inodes.f_files)
    table.append(
        f"{'Disk':<5}{disk_used:>3.0f}% used {disk.free / 2**30:>4.0f} GiB free"
    )
    if disk_used >= _HIGH_PCT:
        issues.append(f"Disk {disk_used:.0f}% full")
    if inodes_used >= _HIGH_PCT:
        issues.append(f"Inodes {inodes_used:.0f}% used")

    if Path("/var/run/reboot-required").exists():
        issues.append("Reboot required")

    if not services:
        issues.append("Services not checked: SYSTEM_SERVICES unset")
    elif (text := _unwrap(states, "Service check", issues)) is not None:
        blocks = text.strip().split("\n\n")
        for block in blocks:
            state = dict(
                line.split("=", 1) for line in block.splitlines() if "=" in line
            )
            if state.get("ActiveState") != "active":
                issues.append(
                    f"{state.get('Id', 'unknown')} "
                    f"{state.get('ActiveState', 'unknown')}"
                )
        if len(blocks) != len(services):
            issues.append("Service check incomplete")
    if (text := _unwrap(failed, "Failed-unit check", issues)) is not None:
        issues.extend(
            f"{line.split()[0]} failed" for line in text.splitlines() if line.strip()
        )

    try:
        if isinstance(alarms, BaseException):
            _unwrap(alarms, "Netdata alerts", issues)
        else:
            payload = alarms  # may be JSON null, which fails below as invalid
            # status=false means health checks are off, so no alerts is not "healthy".
            if payload["status"] is not True:
                raise ValueError("health checks disabled")
            active = [
                a
                for a in payload["alarms"].values()
                if a["status"] in ("WARNING", "CRITICAL")
            ]
            issues.extend(f"{a['status'].title()}: {a['name']}" for a in active[:10])
            if len(active) > 10:
                issues.append(f"{len(active) - 10} more Netdata alerts")
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        log.warning("Netdata alerts invalid: %s", exc)
        issues.append("Netdata alerts invalid or disabled")

    today = datetime.now(ZoneInfo("Europe/Berlin")).date().isoformat()
    lines = [f"*{escape('🖥 System — ' + today)}*"]
    if issues:
        lines.append(escape(f"⚠️ {len(issues)} to check:"))
        # Bounded so the report stays one Telegram message and the code fence
        # below is never split across chunks.
        shown = issues[:_MAX_ISSUES]
        if len(issues) > _MAX_ISSUES:
            shown.append(f"{len(issues) - _MAX_ISSUES} more")
        # 16 lines x 100 chars, doubled by worst-case escaping, stays near 3.2k.
        lines.extend(escape(f"• {issue}"[:100]) for issue in shown)
    else:
        lines.append(escape("✅ All good"))
    # Pre block keeps the columns aligned; its content needs no escaping.
    lines.append("```\n" + "\n".join(table) + "\n```")
    return "\n".join(lines)
