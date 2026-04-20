import httpx

from daily_digest import Item
from daily_digest.config import reddit_user_agent


async def top_of_day(subreddit: str, limit: int) -> list[Item]:
    url = f"https://www.reddit.com/r/{subreddit}/top.json"
    headers = {"User-Agent": reddit_user_agent()}
    params = {"t": "day", "limit": str(limit + 3)}

    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=headers, params=params, timeout=10.0)
        r.raise_for_status()
        payload = r.json()

    items: list[Item] = []
    for child in payload.get("data", {}).get("children", []):
        d = child.get("data", {})
        if d.get("stickied"):
            continue
        title = d.get("title")
        if not title:
            continue
        permalink = d.get("permalink", "")
        link_url = f"https://www.reddit.com{permalink}" if permalink else d.get("url", "")
        items.append(
            Item(
                title=title,
                url=link_url,
                source=f"r/{subreddit}",
                score=d.get("ups", 0),
            )
        )
        if len(items) >= limit:
            break
    return items
