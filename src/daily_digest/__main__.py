import argparse
import asyncio
import logging
import sys
from contextlib import closing

from daily_digest import Item
from daily_digest.config import (
    FEARGREED_EXTREMES,
    MEMES_REDDIT_PER_SUB,
    RSS_FEEDS_NEWS,
    SUBREDDITS_MEMES,
    SUBREDDITS_TECH,
    TECH_HN_LIMIT,
    TECH_REDDIT_PER_SUB,
    feargreed_db_path,
)
from daily_digest.feargreed import CRYPTO, STOCKS, Reading, alert_needed
from daily_digest.format import render, render_feargreed, render_feargreed_alert
from daily_digest.sources import feargreed as feargreed_source
from daily_digest.sources import hackernews, reddit, rss
from daily_digest import store

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


async def _gather_feargreed() -> list[Reading]:
    results = await asyncio.gather(
        feargreed_source.fetch_stocks(),
        feargreed_source.fetch_crypto(),
        return_exceptions=True,
    )
    readings: list[Reading] = []
    for label, result in zip((STOCKS, CRYPTO), results):
        if isinstance(result, Exception):
            log.warning("fear & greed %s failed: %s", label, result)
            continue
        readings.append(result)
    return readings


DIGESTS = {
    "tech": ("🗞", "Tech & ML", _gather_tech),
    "memes": ("😂", "Memes", _gather_memes),
    "news": ("🌍", "World News", _gather_news),
}


async def _run(digest: str, dry_run: bool) -> int:
    emoji, heading, gather = DIGESTS[digest]
    items = await gather()
    text = render(emoji, heading, items)
    if digest == "news":
        readings = await _gather_feargreed()
        if readings:
            text += "\n\n" + render_feargreed(readings)
    if dry_run:
        print(text)
        return 0
    from daily_digest.telegram import send_markdown
    await send_markdown(text)
    log.info("sent %d items for %s", len(items), digest)
    return 0


async def _run_feargreed(dry_run: bool) -> int:
    """Fetch both indices, alert on a fresh crossing into an extreme zone.

    Reads the previous reading before recording the new one, so a run that
    finds the index still parked in the same extreme zone stays quiet.

    Alerts are sent before the readings are recorded: if Telegram is down, the
    run fails with nothing stored and the next hour tries the same crossing
    again. A repeated alert is recoverable, a dropped one is not.

    `--dry-run` reads the database but does not write to it.
    """
    readings = await _gather_feargreed()
    if not readings:
        log.error("fear & greed: both sources failed")
        return 1

    with closing(store.connect(feargreed_db_path())) as conn:
        alerts: list[str] = []
        for reading in readings:
            low, high = FEARGREED_EXTREMES[reading.index]
            previous = store.latest(conn, reading.index)
            if alert_needed(previous, reading, low, high):
                alerts.append(render_feargreed_alert(reading, previous))

        if dry_run:
            print(render_feargreed(readings))
            for text in alerts:
                print()
                print(text)
            return 0

        from daily_digest.telegram import send_markdown
        for text in alerts:
            await send_markdown(text)
        store.record(conn, readings)

    log.info("fear & greed: %d readings, %d alerts", len(readings), len(alerts))
    return 0


async def _run_backfill(dry_run: bool) -> int:
    results = await asyncio.gather(
        feargreed_source.fetch_stocks_history(),
        feargreed_source.fetch_crypto_history(),
        return_exceptions=True,
    )
    readings: list[Reading] = []
    for label, result in zip((STOCKS, CRYPTO), results):
        if isinstance(result, Exception):
            log.warning("fear & greed %s history failed: %s", label, result)
            continue
        readings.extend(result)

    if not readings:
        log.error("fear & greed: no history fetched")
        return 1
    if dry_run:
        print(f"backfill: {len(readings)} readings fetched, nothing written (--dry-run)")
        return 0

    with closing(store.connect(feargreed_db_path())) as conn:
        inserted = store.record(conn, readings)
    print(f"backfill: {len(readings)} readings fetched, {inserted} stored")
    return 0


COMMANDS = [*sorted(DIGESTS), "feargreed"]


async def _dispatch(command: str, dry_run: bool, backfill: bool) -> int:
    if command != "feargreed":
        return await _run(command, dry_run)
    if backfill:
        return await _run_backfill(dry_run)
    return await _run_feargreed(dry_run)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="daily-digest")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--dry-run", action="store_true", help="print to stdout, skip Telegram")
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="feargreed only: load the full published history into the database",
    )
    args = parser.parse_args()
    if args.backfill and args.command != "feargreed":
        parser.error("--backfill is only valid with the feargreed command")
    sys.exit(asyncio.run(_dispatch(args.command, args.dry_run, args.backfill)))


if __name__ == "__main__":
    main()
