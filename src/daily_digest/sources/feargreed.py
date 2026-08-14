"""Fear & Greed source adapters: fetch, map to `Reading`, return.

CNN publishes the stock index, alternative.me the crypto one. Both are
unauthenticated JSON endpoints. Parsing is split from fetching so the parsers
can be tested against saved payloads without a network.

Malformed payloads raise: an endpoint that changed shape is a bug, not an
expected outcome. Callers run these under `asyncio.gather(...,
return_exceptions=True)` and skip the source that failed.
"""

from datetime import datetime, timezone

import httpx

from daily_digest.config import (
    CNN_GRAPH_URL,
    CNN_REFERER,
    CNN_USER_AGENT,
    CRYPTO_FNG_RECENT_LIMIT,
    CRYPTO_FNG_URL,
)
from daily_digest.feargreed import CRYPTO, STOCKS, Reading

_TIMEOUT = 15.0

# Both headers are required: CNN answers 418 if either is missing.
CNN_HEADERS = {"User-Agent": CNN_USER_AGENT, "Referer": CNN_REFERER}


def _value(raw: object) -> int:
    value = round(float(raw))
    if not 0 <= value <= 100:
        raise ValueError(f"fear & greed value out of range: {raw!r}")
    return value


def _optional_value(raw: object | None) -> int | None:
    return None if raw is None else _value(raw)


def _cnn_ts(raw: object) -> datetime:
    """CNN sends ISO-8601 for the current value, epoch millis for history."""
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw / 1000, tz=timezone.utc)
    parsed = datetime.fromisoformat(str(raw))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_cnn(payload: dict) -> Reading:
    current = payload["fear_and_greed"]
    return Reading(
        index=STOCKS,
        value=_value(current["score"]),
        rating=str(current["rating"]).title(),
        ts=_cnn_ts(current["timestamp"]),
        previous_close=_optional_value(current.get("previous_close")),
        previous_week=_optional_value(current.get("previous_1_week")),
        previous_month=_optional_value(current.get("previous_1_month")),
    )


def parse_cnn_history(payload: dict) -> list[Reading]:
    return [
        Reading(
            index=STOCKS,
            value=_value(point["y"]),
            rating=str(point["rating"]).title(),
            ts=_cnn_ts(point["x"]),
        )
        for point in payload["fear_and_greed_historical"]["data"]
    ]


def _crypto_reading(entry: dict) -> Reading:
    return Reading(
        index=CRYPTO,
        value=_value(entry["value"]),
        rating=str(entry["value_classification"]).title(),
        ts=datetime.fromtimestamp(int(entry["timestamp"]), tz=timezone.utc),
    )


def _crypto_value_at(entries: list[dict], offset: int) -> int | None:
    if offset >= len(entries):
        return None
    return _value(entries[offset]["value"])


def parse_crypto(payload: dict) -> Reading:
    """Newest entry, with the comparison values taken from the same response.

    Entries are one per day, newest first, so offset N is N days back.
    """
    entries = payload["data"]
    if not entries:
        raise ValueError("alternative.me returned no data")
    current = _crypto_reading(entries[0])
    return Reading(
        index=current.index,
        value=current.value,
        rating=current.rating,
        ts=current.ts,
        previous_close=_crypto_value_at(entries, 1),
        previous_week=_crypto_value_at(entries, 7),
        previous_month=_crypto_value_at(entries, 30),
    )


def parse_crypto_history(payload: dict) -> list[Reading]:
    return [_crypto_reading(entry) for entry in payload["data"]]


async def _get_cnn() -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(CNN_GRAPH_URL, headers=CNN_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()


async def _get_crypto(limit: int) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(CRYPTO_FNG_URL, params={"limit": limit}, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()


async def fetch_stocks() -> Reading:
    return parse_cnn(await _get_cnn())


async def fetch_crypto() -> Reading:
    return parse_crypto(await _get_crypto(CRYPTO_FNG_RECENT_LIMIT))


async def fetch_stocks_history() -> list[Reading]:
    return parse_cnn_history(await _get_cnn())


async def fetch_crypto_history() -> list[Reading]:
    return parse_crypto_history(await _get_crypto(0))
