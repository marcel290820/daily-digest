"""SQLite history of Fear & Greed readings.

Owns one table, `readings`, keyed by (index, timestamp) so every write is
idempotent: re-running the hourly checker or the backfill changes nothing.
A source that revises a value it already published for that timestamp
overwrites the stored one, so the database never disagrees with the source it
came from. Timestamps are stored as UTC epoch seconds.

Writers are the checker and `--backfill`. The digest only reads the APIs, so
it can never advance the state the alert logic compares against.

Callers own the connection and close it (`contextlib.closing`).
"""

import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from daily_digest.feargreed import Reading

_SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    idx    TEXT    NOT NULL,
    ts     INTEGER NOT NULL,
    value  INTEGER NOT NULL,
    rating TEXT    NOT NULL,
    PRIMARY KEY (idx, ts)
)
"""


def connect(path: str) -> sqlite3.Connection:
    parent = Path(path).parent
    if str(parent) not in ("", "."):
        parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    with conn:
        conn.execute(_SCHEMA)
    return conn


_UPSERT = """
INSERT INTO readings (idx, ts, value, rating) VALUES (?, ?, ?, ?)
ON CONFLICT (idx, ts) DO UPDATE SET value = excluded.value, rating = excluded.rating
WHERE readings.value <> excluded.value OR readings.rating <> excluded.rating
"""


def record(conn: sqlite3.Connection, readings: Iterable[Reading]) -> int:
    """Store readings. Returns how many rows were new or actually changed.

    A reading identical to the stored one is a no-op, so the count is a
    truthful "what did this run add" for the backfill. A reading that revises
    a stored value wins: leaving the old one would make the next check see a
    zone the index has already left and alert on the same crossing again.
    """
    rows = [
        (r.index, int(r.ts.timestamp()), r.value, r.rating) for r in readings
    ]
    if not rows:
        return 0
    with conn:
        cursor = conn.executemany(_UPSERT, rows)
    return cursor.rowcount


def latest(conn: sqlite3.Connection, index: str) -> Reading | None:
    row = conn.execute(
        "SELECT ts, value, rating FROM readings WHERE idx = ? ORDER BY ts DESC LIMIT 1",
        (index,),
    ).fetchone()
    if row is None:
        return None
    ts, value, rating = row
    return Reading(
        index=index,
        value=value,
        rating=rating,
        ts=datetime.fromtimestamp(ts, tz=timezone.utc),
    )
