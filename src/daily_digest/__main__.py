import argparse
import asyncio
import logging
import sys

from daily_digest import Item
from daily_digest.config import (
    MEMES_REDDIT_PER_SUB,
    RSS_FEEDS_NEWS,
    SUBREDDITS_MEMES,
    SUBREDDITS_TECH,
    TECH_HN_LIMIT,
    TECH_REDDIT_PER_SUB,
)
from daily_digest.format import render
from daily_digest.sources import hackernews, reddit, rss

log = logging.getLogger("daily_digest")


async def _gather_tech() -> list[Item]:
    hn_task = hackernews.top_stories(TECH_HN_LIMIT)
    reddit_tasks = [reddit.top_of_day(s, TECH_REDDIT_PER_SUB) for s in SUBREDDITS_TECH]
    results = await asyncio.gather(hn_task, *reddit_tasks, return_exceptions=True)

    items: list[Item] = []
    labels = ["HN", *SUBREDDITS_TECH]
    for label, result in zip(labels, results):
        if isinstance(result, Exception):
            log.warning("source %s failed: %s", label, result)
            continue
        items.extend(result)
    return items


async def _gather_memes() -> list[Item]:
    tasks = [reddit.top_of_day(s, MEMES_REDDIT_PER_SUB) for s in SUBREDDITS_MEMES]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    items: list[Item] = []
    for sub, result in zip(SUBREDDITS_MEMES, results):
        if isinstance(result, Exception):
            log.warning("r/%s failed: %s", sub, result)
            continue
        items.extend(result)
    return items


async def _gather_news() -> list[Item]:
    tasks = [rss.top_entries(name, url, lim) for name, url, lim in RSS_FEEDS_NEWS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    items: list[Item] = []
    for (name, _, _), result in zip(RSS_FEEDS_NEWS, results):
        if isinstance(result, Exception):
            log.warning("feed %s failed: %s", name, result)
            continue
        items.extend(result)
    return items


DIGESTS = {
    "tech": ("🗞", "Tech & ML", _gather_tech),
    "memes": ("😂", "Memes", _gather_memes),
    "news": ("🌍", "World News", _gather_news),
}


async def _run(digest: str, dry_run: bool) -> int:
    emoji, heading, gather = DIGESTS[digest]
    items = await gather()
    text = render(emoji, heading, items)
    if dry_run:
        print(text)
        return 0
    from daily_digest.telegram import send_markdown
    await send_markdown(text)
    log.info("sent %d items for %s", len(items), digest)
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="daily-digest")
    parser.add_argument("digest", choices=sorted(DIGESTS.keys()))
    parser.add_argument("--dry-run", action="store_true", help="print to stdout, skip Telegram")
    args = parser.parse_args()
    sys.exit(asyncio.run(_run(args.digest, args.dry_run)))


if __name__ == "__main__":
    main()
