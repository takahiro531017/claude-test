"""収集 → 相場 → 判定 → 通知 の一連処理。"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from .collector.base import Collector
from .config import Config
from .models import Item
from .notifier.base import Notifier
from .pricing.market import market_for_key
from .pricing.normalizer import normalize_title
from .profit.calculator import calc_profit
from .profit.filters import check_exclusion

log = logging.getLogger(__name__)


@dataclass
class RunStats:
    active: int = 0
    sold: int = 0
    evaluated: int = 0
    candidates: int = 0
    notified: int = 0
    skipped_duplicate: int = 0
    errors: int = 0


def store_items(conn: sqlite3.Connection, items: list[Item], sold: bool, source: str) -> None:
    for i in items:
        i.product_key = normalize_title(i.title)
        if sold:
            conn.execute(
                "INSERT OR REPLACE INTO sold_items(item_id,title,price,sold_at,product_key,source)"
                " VALUES(?,?,?,?,?,?)",
                (i.item_id, i.title, i.price, i.sold_at, i.product_key, source),
            )
        else:
            conn.execute(
                "INSERT OR REPLACE INTO listings(item_id,title,price,condition,shipping_payer,listed_at,"
                "url,image_url,category,description,size_class,product_key,source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (i.item_id, i.title, i.price, i.condition, i.shipping_payer, i.listed_at, i.url,
                 i.image_url, i.category, i.description, i.size_class, i.product_key, source),
            )
    conn.commit()


def run_pipeline(
    conn: sqlite3.Connection,
    collector: Collector,
    notifiers: list[Notifier],
    cfg: Config,
    now: datetime | None = None,
    source: str = "csv",
) -> RunStats:
    st = RunStats()
    active, sold = list(collector.fetch_active()), list(collector.fetch_sold())
    st.active, st.sold = len(active), len(sold)
    store_items(conn, sold, True, source)
    store_items(conn, active, False, source)
    log.info("取得件数: 販売中=%d 売り切れ=%d", st.active, st.sold)

    for item in active:
        try:
            if not (cfg.price_min <= item.price <= cfg.price_max):
                continue
            reason = check_exclusion(item, cfg.exclude)
            st.evaluated += 1
            market = market_for_key(conn, item.product_key, cfg.market, now)
            verdict = calc_profit(item, market, cfg.profit) if not reason else None
            ok = bool(verdict and verdict.ok)
            conn.execute(
                "INSERT INTO evaluations(item_id,median_price,sample_count,confidence,net_profit,"
                "profit_rate,verdict,reject_reason) VALUES(?,?,?,?,?,?,?,?)",
                (item.item_id, market.median if market else None, market.count if market else 0,
                 "high" if market and market.reliable else "low",
                 verdict.net_profit if verdict else None, verdict.margin_rate if verdict else None,
                 "ok" if ok else "ng", reason or (verdict.reason if verdict else "")),
            )
            conn.commit()
            if not ok:
                continue
            st.candidates += 1
            if conn.execute("SELECT 1 FROM notifications WHERE item_id=?", (item.item_id,)).fetchone():
                st.skipped_duplicate += 1
                continue
            sent = [n.name for n in notifiers if n.send(item, market, verdict)]
            if sent:
                conn.execute("INSERT INTO notifications(item_id,channel) VALUES(?,?)",
                             (item.item_id, ",".join(sent)))
                conn.commit()
                st.notified += 1
            else:
                st.errors += 1
        except Exception:
            st.errors += 1
            log.exception("商品評価中にエラー item_id=%s", item.item_id)
    log.info("完了: %s", st)
    return st
