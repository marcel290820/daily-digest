import asyncio

import feedparser
import httpx

from daily_digest import Item


async def top_entries(source_name: str, feed_url: str, limit: int) -> list[Item]:
    async with httpx.AsyncClient() as client:
        r = await client.get(feed_url, timeout=15.0, follow_redirects=True)
        r.raise_for_status()
        body = r.content

    parsed = await asyncio.to_thread(feedparser.parse, body)
    items: list[Item] = []
    for entry in parsed.entries[:limit]:
        title = getattr(entry, "title", None)
        link = getattr(entry, "link", None)
        if not title or not link:
            continue
        items.append(Item(title=title, url=link, source=source_name, score=None))
    return items
