from __future__ import annotations

import sqlite3
import statistics
from datetime import datetime, timedelta

from ..config import MarketConfig
from ..models import MarketStat


def compute_market(prices: list[int], cfg: MarketConfig) -> MarketStat | None:
    """外れ値(上下 trim_ratio)を除外した中央値。件数は除外前の実件数。"""
    n = len(prices)
    if n == 0:
        return None
    s = sorted(prices)
    k = int(n * cfg.trim_ratio)
    trimmed = s[k : n - k] or s
    return MarketStat(median=int(statistics.median(trimmed)), count=n, reliable=n >= cfg.min_samples)


def market_for_key(
    conn: sqlite3.Connection, product_key: str, cfg: MarketConfig, now: datetime | None = None
) -> MarketStat | None:
    if not product_key:
        return None
    since = ((now or datetime.now()) - timedelta(days=cfg.window_days)).strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT price FROM sold_items WHERE product_key=? AND substr(sold_at,1,10)>=?",
        (product_key, since),
    ).fetchall()
    return compute_market([r["price"] for r in rows], cfg)
