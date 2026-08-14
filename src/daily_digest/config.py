import os

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


def reddit_user_agent() -> str:
    return os.environ.get("REDDIT_USER_AGENT", "daily-digest/0.1")


def feargreed_db_path() -> str:
    return os.environ.get("DIGEST_DB_PATH", "feargreed.db")


SUBREDDITS_TECH: tuple[str, ...] = ("MachineLearning", "technology", "CryptoCurrency")
SUBREDDITS_MEMES: tuple[str, ...] = ("memes", "dankmemes")

RSS_FEEDS_NEWS: tuple[tuple[str, str, int], ...] = (
    ("Tagesschau", "https://www.tagesschau.de/xml/rss2", 5),
    ("Handelsblatt", "https://www.handelsblatt.com/contentexport/feed/schlagzeilen", 5),
)

TECH_HN_LIMIT = 5
TECH_REDDIT_PER_SUB = 2
MEMES_REDDIT_PER_SUB = 5

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
