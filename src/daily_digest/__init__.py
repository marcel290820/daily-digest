from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    title: str
    url: str
    source: str
    score: int | None = None
