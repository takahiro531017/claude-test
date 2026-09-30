from __future__ import annotations

import csv
import math
import sqlite3
from datetime import date, datetime
from pathlib import Path

EXPORT_COLUMNS = [
    "id", "item_id", "title", "status", "purchased_at", "purchase_price", "listed_at",
    "listed_price", "sold_at", "sold_price", "fee", "shipping_cost", "packing_cost", "profit", "memo",
]


def _today() -> str:
    return date.today().isoformat()


def add_purchase(conn: sqlite3.Connection, title: str, purchase_price: int, item_id: str = "",
                 product_key: str = "", purchased_at: str | None = None, memo: str = "") -> int:
    cur = conn.execute(
        "INSERT INTO inventory(item_id,product_key,title,status,purchase_price,purchased_at,memo)"
        " VALUES(?,?,?,'purchased',?,?,?)",
        (item_id, product_key, title, purchase_price, purchased_at or _today(), memo))
    conn.commit()
    return cur.lastrowid


def _get(conn, inv_id: int, allowed: tuple[str, ...]):
    row = conn.execute("SELECT * FROM inventory WHERE id=?", (inv_id,)).fetchone()
    if row is None:
        raise ValueError(f"在庫ID {inv_id} が見つかりません")
    if row["status"] not in allowed:
        raise ValueError(f"在庫ID {inv_id} は状態 {row['status']} のため操作できません")
    return row


def mark_listed(conn, inv_id: int, listed_price: int, listed_at: str | None = None) -> None:
    _get(conn, inv_id, ("purchased", "listed"))
    conn.execute("UPDATE inventory SET status='listed', listed_price=?, listed_at=? WHERE id=?",
                 (listed_price, listed_at or _today(), inv_id))
    conn.commit()


def mark_sold(conn, inv_id: int, sold_price: int, sold_at: str | None = None, fee: int | None = None,
              shipping_cost: int = 0, packing_cost: int = 0, fee_rate: float = 0.10) -> None:
    _get(conn, inv_id, ("purchased", "listed"))
    if fee is None:
        fee = math.floor(sold_price * fee_rate)
    conn.execute(
        "UPDATE inventory SET status='sold', sold_price=?, sold_at=?, fee=?, shipping_cost=?,"
        " packing_cost=? WHERE id=?",
        (sold_price, sold_at or _today(), fee, shipping_cost, packing_cost, inv_id))
    conn.commit()


def row_profit(r) -> int | None:
    if r["status"] != "sold":
        return None
    return (r["sold_price"] or 0) - (r["purchase_price"] or 0) - (r["fee"] or 0) \
        - (r["shipping_cost"] or 0) - (r["packing_cost"] or 0)


def _days(a: str, b: str) -> int:
    return (datetime.fromisoformat(b[:10]) - datetime.fromisoformat(a[:10])).days


def monthly_report(conn: sqlite3.Connection) -> list[dict]:
    """売却月ごとの 売上・利益・件数・平均回転日数(仕入れ→売却)。"""
    out: dict[str, dict] = {}
    for r in conn.execute("SELECT * FROM inventory WHERE status='sold' ORDER BY sold_at"):
        m = r["sold_at"][:7]
        d = out.setdefault(m, {"month": m, "count": 0, "revenue": 0, "profit": 0, "_days": []})
        d["count"] += 1
        d["revenue"] += r["sold_price"] or 0
        d["profit"] += row_profit(r)
        if r["purchased_at"]:
            d["_days"].append(_days(r["purchased_at"], r["sold_at"]))
    for d in out.values():
        days = d.pop("_days")
        d["avg_turnover_days"] = round(sum(days) / len(days), 1) if days else None
    return list(out.values())


def stagnant_stock(conn: sqlite3.Connection, days: int = 30, today: str | None = None) -> list[dict]:
    """仕入れから days 日以上経っても売れていない在庫。"""
    t = today or _today()
    res = []
    for r in conn.execute("SELECT * FROM inventory WHERE status IN ('purchased','listed')"):
        age = _days(r["purchased_at"], t) if r["purchased_at"] else 0
        if age >= days:
            res.append({"id": r["id"], "title": r["title"], "status": r["status"],
                        "purchase_price": r["purchase_price"], "age_days": age})
    return sorted(res, key=lambda x: -x["age_days"])


def export_csv(conn: sqlite3.Connection, path: str | Path, year: int | None = None) -> int:
    """確定申告用CSV。year 指定時は売却年(未売却は仕入れ年)で絞る。"""
    n = 0
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EXPORT_COLUMNS)
        w.writeheader()
        for r in conn.execute("SELECT * FROM inventory ORDER BY id"):
            ref = (r["sold_at"] if r["status"] == "sold" else r["purchased_at"]) or ""
            if year and not ref.startswith(str(year)):
                continue
            row = {k: r[k] for k in EXPORT_COLUMNS if k in r.keys()}
            row["profit"] = row_profit(r)
            w.writerow(row)
            n += 1
    return n
