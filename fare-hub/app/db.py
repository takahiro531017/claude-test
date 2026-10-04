"""SQLite スキーマと接続。DB ファイルは data/ 配下（Git管理外）。"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .config import ROOT

SCHEMA = """
CREATE TABLE IF NOT EXISTS tariffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origin TEXT NOT NULL,                 -- 発地拠点
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    profile TEXT,
    valid_from TEXT, valid_to TEXT,       -- ISO日付
    customer_code TEXT, quote_no TEXT, payment_terms TEXT, closing_day TEXT,
    imported_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rates (        -- 発地拠点 × 着地地帯 × サイズ -> 運賃(税別円)
    tariff_id INTEGER NOT NULL REFERENCES tariffs(id) ON DELETE CASCADE,
    region TEXT NOT NULL, size INTEGER NOT NULL, price INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'parsed',  -- parsed | manual
    PRIMARY KEY (tariff_id, region, size)
);
CREATE TABLE IF NOT EXISTS weights (
    tariff_id INTEGER NOT NULL REFERENCES tariffs(id) ON DELETE CASCADE,
    size INTEGER NOT NULL, weight_kg REAL NOT NULL,
    PRIMARY KEY (tariff_id, size)
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tariff_id INTEGER NOT NULL REFERENCES tariffs(id) ON DELETE CASCADE,
    category TEXT NOT NULL, text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS warnings (     -- パース時の警告（構造情報のみ。欠損セルは都度計算）
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tariff_id INTEGER NOT NULL REFERENCES tariffs(id) ON DELETE CASCADE,
    kind TEXT NOT NULL, detail TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tariffs_origin ON tariffs(origin);
"""


def default_db_path() -> Path:
    return Path(os.environ.get("FARE_HUB_DB", ROOT / "data" / "fare_hub.sqlite"))


def connect(path: Path | str) -> sqlite3.Connection:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, check_same_thread=False)  # 1リクエスト1接続で逐次利用
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
