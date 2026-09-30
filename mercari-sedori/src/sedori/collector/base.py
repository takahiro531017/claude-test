from __future__ import annotations

from typing import Iterable, Protocol

from ..models import Item


class Collector(Protocol):
    """収集手段の差し替え口。CSV / Playwright などが実装する。"""

    def fetch_active(self) -> Iterable[Item]: ...

    def fetch_sold(self) -> Iterable[Item]: ...
