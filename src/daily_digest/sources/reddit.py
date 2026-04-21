import asyncio

import feedparser
import httpx

from daily_digest import Item
from daily_digest.config import reddit_user_agent


async def top_of_day(subreddit: str, limit: int) -> list[Item]:
    ua = reddit_user_agent()
    url = f"https://www.reddit.com/r/{subreddit}/top.rss"
    params = {"t": "day", "limit": str(limit + 3)}

    async with httpx.AsyncClient() as client:
        r = await client.get(
            url,
            params=params,
            headers={"User-Agent": ua},
            timeout=15.0,
            follow_redirects=True,
        )
        r.raise_for_status()
        body = r.content

    parsed = await asyncio.to_thread(feedparser.parse, body)
    items: list[Item] = []
    for entry in parsed.entries:
        title = getattr(entry, "title", None)
        link = getattr(entry, "link", None)
        if not title or not link:
            continue
        items.append(Item(title=title, url=link, source=f"r/{subreddit}", score=None))
        if len(items) >= limit:
            break
    return items
