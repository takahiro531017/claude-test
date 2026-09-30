from __future__ import annotations

from typing import Protocol

from ..models import Item, MarketStat, Verdict


class Notifier(Protocol):
    name: str

    def send(self, item: Item, market: MarketStat, verdict: Verdict) -> bool: ...
