import logging

import httpx

from daily_digest.config import telegram_bot_token, telegram_chat_id

log = logging.getLogger("daily_digest.telegram")

_MAX_LEN = 4096


def _split(text: str) -> list[str]:
    if len(text) <= _MAX_LEN:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > _MAX_LEN:
        cut = remaining.rfind("\n", 0, _MAX_LEN)
        if cut <= 0:
            cut = _MAX_LEN
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


async def send_markdown(text: str) -> None:
    token = telegram_bot_token()
    chat_id = telegram_chat_id()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient() as client:
        for chunk in _split(text):
            r = await client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": "MarkdownV2",
                    "disable_web_page_preview": True,
                },
                timeout=15.0,
            )
            if r.is_error:
                log.error("Telegram error %s: %s", r.status_code, r.text)
            r.raise_for_status()
