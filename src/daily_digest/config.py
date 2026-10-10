import os
import re
from datetime import date

from daily_digest.feargreed import CRYPTO, STOCKS


def _required_env(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(
            f"Missing required env var: {key}. "
            f"Set it in /etc/daily-digest/env or export locally."
        )
    return val


def telegram_bot_token() -> str:
    return _required_env("TELEGRAM_BOT_TOKEN")


def telegram_chat_id() -> str:
    return _required_env("TELEGRAM_CHAT_ID")


def feargreed_db_path() -> str:
    return os.environ.get("DIGEST_DB_PATH", "feargreed.db")


def birth_date() -> date | None:
    """Optional. Unset skips the life line; a malformed value raises."""
    val = os.environ.get("BIRTH_DATE")
    return date.fromisoformat(val) if val else None


def system_services() -> tuple[str, ...]:
    """Comma-separated service names, without `.service`. Unset checks none."""
    names = tuple(
        n.strip() for n in os.environ.get("SYSTEM_SERVICES", "").split(",") if n.strip()
    )
    # A leading "-" would reach systemctl as an option, not a unit name.
    if bad := [n for n in names if not re.fullmatch(r"[\w@.:][\w@.:-]*", n)]:
        raise ValueError(f"Invalid SYSTEM_SERVICES entries: {bad}")
    return names


RSS_FEEDS_NEWS: tuple[tuple[str, str, int], ...] = (
    ("Tagesschau", "https://www.tagesschau.de/xml/rss2", 5),
    ("Handelsblatt", "https://www.handelsblatt.com/contentexport/feed/schlagzeilen", 5),
)

TECH_HN_LIMIT = 10

# Unofficial CNN endpoint. It answers 418 ("I'm a teapot. You're a bot.")
# unless both a browser User-Agent and a cnn.com Referer are sent.
CNN_GRAPH_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
CNN_REFERER = "https://edition.cnn.com/"
CNN_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

CRYPTO_FNG_URL = "https://api.alternative.me/fng/"
# One entry per day, newest first. 31 covers today plus a 30-day comparison;
# 0 means the full history (back to 2018) and is only used by --backfill.
CRYPTO_FNG_RECENT_LIMIT = 31

# Extreme zone bounds per index: (extreme fear at or below, extreme greed at
# or above). Crypto is stricter because it parks in its extreme zones for
# weeks at a time during a trend, and a wider band would alert every day.
FEARGREED_EXTREMES: dict[str, tuple[int, int]] = {
    STOCKS: (20, 80),
    CRYPTO: (10, 90),
}
