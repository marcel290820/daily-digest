from datetime import date

from daily_digest import Item
from daily_digest.feargreed import INDEX_LABELS, Reading

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
        return f"\\[{escape(f'{item.score / 1000:.1f}k')}\\] "
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


def _feargreed_line(reading: Reading) -> str:
    parts = [
        f"*{escape(INDEX_LABELS[reading.index])}* {reading.value} {escape(reading.rating)}"
    ]
    history = (
        ("prev", reading.previous_close),
        ("1w", reading.previous_week),
        ("1m", reading.previous_month),
    )
    parts.extend(f"{label} {value}" for label, value in history if value is not None)
    return " \\| ".join(parts)


def render_feargreed(readings: list[Reading]) -> str:
    lines = [f"*{escape('📊 Fear & Greed')}*"]
    lines.extend(_feargreed_line(r) for r in readings)
    return "\n".join(lines)


def render_feargreed_alert(current: Reading, previous: Reading | None) -> str:
    label = INDEX_LABELS[current.index]
    if previous is None:
        context = escape("(first reading)")
    else:
        context = escape(f"(was {previous.value}, {previous.rating})")
    return (
        f"*{escape('🚨 ' + label + ' Fear & Greed')}*\n"
        f"*{current.value}* {escape(current.rating)} {context}"
    )
