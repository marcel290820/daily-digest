"""Fear & Greed domain types and zone rules.

Pure: no network, no database, no clock. Callers hand in readings and
thresholds, this returns zones and alert decisions. Thresholds live in
`config` because they differ per index.
"""

from dataclasses import dataclass
from datetime import datetime

STOCKS = "stocks"
CRYPTO = "crypto"

INDEX_LABELS = {STOCKS: "Stocks", CRYPTO: "Crypto"}

ZONE_EXTREME_FEAR = "extreme_fear"
ZONE_NORMAL = "normal"
ZONE_EXTREME_GREED = "extreme_greed"


@dataclass(frozen=True)
class Reading:
    """One index value at one point in time.

    `value` is 0-100, already rounded to an integer at the source boundary so
    the number shown, the number stored and the number compared to a threshold
    are the same one. The `previous_*` fields come from the live API response
    and are display-only; they are never persisted.
    """

    index: str
    value: int
    rating: str
    ts: datetime
    previous_close: int | None = None
    previous_week: int | None = None
    previous_month: int | None = None


def zone(value: int, low: int, high: int) -> str:
    if value <= low:
        return ZONE_EXTREME_FEAR
    if value >= high:
        return ZONE_EXTREME_GREED
    return ZONE_NORMAL


def alert_needed(
    previous: Reading | None, current: Reading, low: int, high: int
) -> bool:
    """True when `current` entered an extreme zone the previous reading was not in.

    `previous` is None when no earlier reading exists (first run, empty
    database); an extreme value then counts as a crossing. Staying inside the
    same extreme zone does not re-alert; leaving and re-entering does.
    """
    current_zone = zone(current.value, low, high)
    if current_zone == ZONE_NORMAL:
        return False
    return previous is None or current_zone != zone(previous.value, low, high)
