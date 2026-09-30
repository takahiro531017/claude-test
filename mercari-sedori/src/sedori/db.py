from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings(
  item_id TEXT PRIMARY KEY, title TEXT, price INTEGER, condition TEXT,
  shipping_payer TEXT, listed_at TEXT, url TEXT, image_url TEXT, category TEXT,
  description TEXT, size_class TEXT, product_key TEXT, fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
  source TEXT);
CREATE TABLE IF NOT EXISTS sold_items(
  item_id TEXT PRIMARY KEY, title TEXT, price INTEGER, sold_at TEXT,
  product_key TEXT, source TEXT);
CREATE INDEX IF NOT EXISTS idx_sold_key ON sold_items(product_key, sold_at);
CREATE TABLE IF NOT EXISTS evaluations(
  id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT, median_price INTEGER,
  sample_count INTEGER, confidence TEXT, net_profit INTEGER, profit_rate REAL,
  verdict TEXT, reject_reason TEXT, evaluated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS notifications(
  item_id TEXT PRIMARY KEY, notified_at TEXT DEFAULT CURRENT_TIMESTAMP, channel TEXT);
CREATE TABLE IF NOT EXISTS inventory(
  id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT, product_key TEXT, title TEXT,
  status TEXT CHECK(status IN ('purchased','listed','sold')),
  purchase_price INTEGER, purchased_at TEXT, listed_price INTEGER, listed_at TEXT,
  sold_price INTEGER, sold_at TEXT, fee INTEGER, shipping_cost INTEGER,
  packing_cost INTEGER, memo TEXT);
CREATE TABLE IF NOT EXISTS request_log(ts TEXT DEFAULT CURRENT_TIMESTAMP, kind TEXT);
"""


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(listings)")}
    if "size_class" not in cols:  # 旧スキーマからの移行
        conn.execute("ALTER TABLE listings ADD COLUMN size_class TEXT")
    return conn
