import asyncio

import httpx

from daily_digest import Item

_BASE = "https://hacker-news.firebaseio.com/v0"


async def _fetch_item(client: httpx.AsyncClient, item_id: int) -> dict | None:
    r = await client.get(f"{_BASE}/item/{item_id}.json", timeout=10.0)
    r.raise_for_status()
    return r.json()


async def top_stories(limit: int) -> list[Item]:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{_BASE}/topstories.json", timeout=10.0)
        r.raise_for_status()
        ids: list[int] = r.json()

        candidates = ids[: limit * 3]
        raw = await asyncio.gather(
            *(_fetch_item(client, i) for i in candidates),
            return_exceptions=True,
        )

    items: list[Item] = []
    for obj in raw:
        if not isinstance(obj, dict):
            continue
        if obj.get("type") != "story":
            continue
        if obj.get("dead") or obj.get("deleted"):
            continue
        title = obj.get("title")
        if not title:
            continue
        url = obj.get("url") or f"https://news.ycombinator.com/item?id={obj['id']}"
        items.append(
            Item(title=title, url=url, source="HN", score=obj.get("score", 0))
        )
        if len(items) >= limit:
            break
    return items
