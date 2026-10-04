"""取込・集約・検索・比較のロジック。"""
from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import PurePosixPath, PureWindowsPath

from .config import Settings
from .parser import ParseError, parse_date, parse_pdf

log = logging.getLogger("fare_hub")

META_FIELDS = ("origin", "valid_from", "valid_to", "customer_code", "quote_no", "payment_terms", "closing_day")


def safe_filename(name: str) -> str:
    base = PureWindowsPath(PurePosixPath(name or "").name).name
    return re.sub(r"[\x00-\x1f]", "", base)[:200] or "unnamed.pdf"


# ------------------------------------------------------------------ 期限
def status_of(valid_from: str | None, valid_to: str | None, today: date, soon_days: int) -> str:
    """active / expiring（期限間近） / expired / upcoming / unknown（期日不明）"""
    if not valid_from and not valid_to:
        return "unknown"
    if valid_from and today < date.fromisoformat(valid_from):
        return "upcoming"
    if valid_to:
        vt = date.fromisoformat(valid_to)
        if today > vt:
            return "expired"
        if today + timedelta(days=soon_days) >= vt:
            return "expiring"
    return "active"


def _decorate(row: sqlite3.Row, st: Settings, today: date) -> dict:
    d = dict(row)
    d["status"] = status_of(d["valid_from"], d["valid_to"], today, st.parser["expiring_soon_days"])
    return d


# ------------------------------------------------------------------ 取込
def import_pdf(conn: sqlite3.Connection, st: Settings, filename: str, data: bytes) -> dict:
    fname = safe_filename(filename)
    sha = hashlib.sha256(data).hexdigest()
    dup = conn.execute("SELECT id FROM tariffs WHERE sha256=?", (sha,)).fetchone()
    if dup:
        log.info("import file=%s status=duplicate", fname)
        return {"filename": fname, "status": "duplicate", "tariff_id": dup["id"], "warnings": []}
    try:
        res = parse_pdf(data, st)
    except ParseError as e:
        log.warning("import file=%s status=error kind=%s", fname, e.kind)
        return {"filename": fname, "status": "error", "error": e.kind}
    except Exception as e:  # 想定外。型名のみ記録
        log.warning("import file=%s status=error kind=%s", fname, type(e).__name__)
        return {"filename": fname, "status": "error", "error": f"unexpected:{type(e).__name__}"}

    warnings = list(res.warnings)
    origin = "".join(res.header.get("origin", "").split())
    if not origin:
        origin = re.sub(r"\.pdf$", "", fname, flags=re.I)
        warnings.append({"kind": "origin_from_filename", "detail": ""})
    vf = res.header.get("valid_from")
    with conn:
        if vf:  # 同一拠点・同一適用期日は再取込として置換
            conn.execute("DELETE FROM tariffs WHERE origin=? AND valid_from=?", (origin, vf))
        cur = conn.execute(
            "INSERT INTO tariffs(origin,filename,sha256,profile,valid_from,valid_to,customer_code,"
            "quote_no,payment_terms,closing_day,imported_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (origin, fname, sha, res.profile, vf, res.header.get("valid_to"),
             res.header.get("customer_code"), res.header.get("quote_no"),
             res.header.get("payment_terms"), res.header.get("closing_day"),
             datetime.now().isoformat(timespec="seconds")),
        )
        tid = cur.lastrowid
        conn.executemany("INSERT INTO rates(tariff_id,region,size,price) VALUES (?,?,?,?)",
                         [(tid, r, s, p) for (r, s), p in res.rates.items()])
        conn.executemany("INSERT INTO weights VALUES (?,?,?)", [(tid, s, w) for s, w in res.weights.items()])
        conn.executemany("INSERT INTO notes(tariff_id,category,text) VALUES (?,?,?)",
                         [(tid, c, t) for c, t in res.notes])
        conn.executemany("INSERT INTO warnings(tariff_id,kind,detail) VALUES (?,?,?)",
                         [(tid, w["kind"], w["detail"]) for w in warnings])
    missing = missing_cells(conn, st, tid)
    log.info("import file=%s status=ok cells=%d missing=%d warnings=%d profile=%s",
             fname, len(res.rates), len(missing), len(warnings), res.profile)
    return {"filename": fname, "status": "ok", "tariff_id": tid, "origin": origin,
            "cells": len(res.rates), "missing": len(missing), "warnings": warnings}


# ------------------------------------------------------------------ 参照
def missing_cells(conn, st: Settings, tid: int) -> list[dict]:
    have = {(r["region"], r["size"]) for r in conn.execute("SELECT region,size FROM rates WHERE tariff_id=?", (tid,))}
    return [{"region": r, "size": s} for r in st.region_names for s in st.sizes if (r, s) not in have]


def list_tariffs(conn, st: Settings, today: date) -> list[dict]:
    out = []
    for row in conn.execute("SELECT * FROM tariffs ORDER BY origin, valid_from DESC"):
        d = _decorate(row, st, today)
        d["missing"] = len(missing_cells(conn, st, d["id"]))
        d["warning_count"] = conn.execute("SELECT COUNT(*) FROM warnings WHERE tariff_id=?", (d["id"],)).fetchone()[0]
        out.append(d)
    return out


def current_tariffs(conn, st: Settings, today: date) -> list[dict]:
    """拠点ごとに、基準日に有効な運賃表（無ければ直近のもの）を1つ選ぶ。"""
    rank = {"active": 0, "expiring": 0, "unknown": 0, "upcoming": 1, "expired": 2}
    best: dict[str, dict] = {}
    for row in conn.execute("SELECT * FROM tariffs"):
        d = _decorate(row, st, today)
        key = (rank[d["status"]], -(int(d["valid_from"].replace("-", "")) if d["valid_from"] else 0))
        if d["origin"] not in best or key < best[d["origin"]]["_key"]:
            d["_key"] = key
            best[d["origin"]] = d
    out = sorted(best.values(), key=lambda d: d["origin"])
    for d in out:
        d.pop("_key")
    return out


def get_tariff(conn, st: Settings, tid: int, today: date) -> dict | None:
    row = conn.execute("SELECT * FROM tariffs WHERE id=?", (tid,)).fetchone()
    if not row:
        return None
    d = _decorate(row, st, today)
    rates: dict[str, dict[str, dict]] = {r: {} for r in st.region_names}
    for r in conn.execute("SELECT region,size,price,source FROM rates WHERE tariff_id=?", (tid,)):
        rates.setdefault(r["region"], {})[str(r["size"])] = {"price": r["price"], "source": r["source"]}
    d.update(
        sizes=st.sizes, regions=st.region_names, rates=rates,
        weights={str(r["size"]): r["weight_kg"] for r in conn.execute("SELECT size,weight_kg FROM weights WHERE tariff_id=?", (tid,))},
        missing=missing_cells(conn, st, tid),
        warnings=[dict(r) for r in conn.execute("SELECT kind,detail FROM warnings WHERE tariff_id=?", (tid,))],
        notes=[dict(r) for r in conn.execute("SELECT category,text FROM notes WHERE tariff_id=? ORDER BY id", (tid,))],
    )
    return d


def delete_tariff(conn, tid: int) -> bool:
    with conn:
        return conn.execute("DELETE FROM tariffs WHERE id=?", (tid,)).rowcount > 0


# ------------------------------------------------------------------ 手動補正
def set_rate(conn, st: Settings, tid: int, region: str, size: int, price: int | None) -> None:
    if region not in st.region_names or size not in st.sizes:
        raise ValueError("unknown_region_or_size")
    if price is not None and not 1 <= price <= 1_000_000:
        raise ValueError("price_out_of_range")
    if not conn.execute("SELECT 1 FROM tariffs WHERE id=?", (tid,)).fetchone():
        raise LookupError("tariff_not_found")
    with conn:
        if price is None:
            conn.execute("DELETE FROM rates WHERE tariff_id=? AND region=? AND size=?", (tid, region, size))
        else:
            conn.execute(
                "INSERT INTO rates(tariff_id,region,size,price,source) VALUES (?,?,?,?, 'manual') "
                "ON CONFLICT(tariff_id,region,size) DO UPDATE SET price=excluded.price, source='manual'",
                (tid, region, size, price))


def update_meta(conn, tid: int, fields: dict) -> None:
    sets, vals = [], []
    for k, v in fields.items():
        if k not in META_FIELDS:
            raise ValueError("unknown_field")
        v = (v or "").strip() or None
        if k in ("valid_from", "valid_to") and v is not None:
            if parse_date(v) != v:
                raise ValueError("invalid_date")
        if k == "origin" and not v:
            raise ValueError("origin_required")
        sets.append(f"{k}=?")
        vals.append(v)
    if not sets:
        return
    with conn:
        n = conn.execute(f"UPDATE tariffs SET {','.join(sets)} WHERE id=?", (*vals, tid)).rowcount
    if not n:
        raise LookupError("tariff_not_found")


# ------------------------------------------------------------------ 統合・比較
def combined_rows(conn, st: Settings, today: date, origin: str | None = None) -> list[dict]:
    """発地拠点 × 着地地帯 × サイズ -> 運賃 の統合データ（現行運賃表のみ）。"""
    rows = []
    for t in current_tariffs(conn, st, today):
        if origin and t["origin"] != origin:
            continue
        weights = {r["size"]: r["weight_kg"] for r in conn.execute("SELECT size,weight_kg FROM weights WHERE tariff_id=?", (t["id"],))}
        rates = {(r["region"], r["size"]): (r["price"], r["source"]) for r in conn.execute(
            "SELECT region,size,price,source FROM rates WHERE tariff_id=?", (t["id"],))}
        for region in st.region_names:
            for size in st.sizes:
                p = rates.get((region, size))
                rows.append({
                    "tariff_id": t["id"], "origin": t["origin"], "region": region, "size": size,
                    "weight_kg": weights.get(size), "price": p[0] if p else None,
                    "source": p[1] if p else None, "status": t["status"],
                    "valid_from": t["valid_from"], "valid_to": t["valid_to"],
                    "quote_no": t["quote_no"], "customer_code": t["customer_code"],
                })
    return rows


def cheapest(rows: list[dict]) -> dict[tuple[str, int], int]:
    """(地帯, サイズ) ごとの最安値。期限切れ・未適用は比較対象外（有効な候補が無いセルのみ全体から）。"""
    valid: dict[tuple[str, int], int] = {}
    anyone: dict[tuple[str, int], int] = {}
    for r in rows:
        if r["price"] is None:
            continue
        k = (r["region"], r["size"])
        anyone[k] = min(r["price"], anyone.get(k, r["price"]))
        if r["status"] not in ("expired", "upcoming"):
            valid[k] = min(r["price"], valid.get(k, r["price"]))
    return {**anyone, **valid}


def lookup(conn, st: Settings, today: date, dest: str, size: int | None, origin: str | None) -> dict:
    dst = st.resolve_destination(dest)
    out = {"destination": dst, "size": size, "results": [], "cheapest": {}}
    if not dst["region"]:
        return out
    rows = [r for r in combined_rows(conn, st, today, origin) if r["region"] == dst["region"]]
    best = cheapest(rows)
    by_origin: dict[str, dict] = {}
    for r in rows:
        o = by_origin.setdefault(r["origin"], {
            "tariff_id": r["tariff_id"], "origin": r["origin"], "status": r["status"],
            "valid_from": r["valid_from"], "valid_to": r["valid_to"], "prices": {}})
        o["prices"][str(r["size"])] = r["price"]
    out["results"] = sorted(by_origin.values(), key=lambda o: o["origin"])
    out["cheapest"] = {str(s): p for (reg, s), p in best.items()}
    return out
