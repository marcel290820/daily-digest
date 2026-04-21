from datetime import date

from daily_digest import Item

_MDV2_RESERVED = r"_*[]()~`>#+-=|{}.!\\"
_ESCAPE_TABLE = str.maketrans({c: "\\" + c for c in _MDV2_RESERVED})


def escape(text: str) -> str:
    return text.translate(_ESCAPE_TABLE)


def _escape_url(url: str) -> str:
    return url.replace("\\", "\\\\").replace(")", "\\)")


def _score_tag(item: Item) -> str:
    if item.score is None:
        return ""
    if item.score >= 1000:
        return f"\\[{item.score / 1000:.1f}k\\] "
    return f"\\[{item.score}\\] "


def render(heading_emoji: str, heading: str, items: list[Item]) -> str:
    today = date.today().isoformat()
    lines = [f"*{escape(heading_emoji + ' ' + heading)} — {escape(today)}*", ""]
    if not items:
        lines.append(escape("(no items today)"))
        return "\n".join(lines)

    for i, item in enumerate(items, 1):
        line = (
            f"{i}\\. {_score_tag(item)}"
            f"[{escape(item.title)}]({_escape_url(item.url)}) — `{escape(item.source)}`"
        )
        lines.append(line)
    return "\n".join(lines)
