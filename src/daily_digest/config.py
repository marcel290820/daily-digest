import os


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


SUBREDDITS_TECH: tuple[str, ...] = ("MachineLearning", "technology", "CryptoCurrency")
SUBREDDITS_MEMES: tuple[str, ...] = ("memes", "dankmemes")

RSS_FEEDS_NEWS: tuple[tuple[str, str, int], ...] = (
    ("Tagesschau", "https://www.tagesschau.de/xml/rss2", 3),
    ("Handelsblatt", "https://www.handelsblatt.com/contentexport/feed/schlagzeilen", 2),
)

TECH_HN_LIMIT = 5
TECH_REDDIT_PER_SUB = 2
MEMES_REDDIT_PER_SUB = 5
