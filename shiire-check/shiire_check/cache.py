"""ローカルSQLite: 読み取り結果キャッシュ・手修正・確認済み状態。外部には送信しない。"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from shiire_check.schema import ReadResult


class Cache:
    def __init__(self, path: Path | str):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        with self._lock, self._db:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS readings(
                    key TEXT, reader_id TEXT, json TEXT, created REAL,
                    PRIMARY KEY(key, reader_id));
                CREATE TABLE IF NOT EXISTS corrections(
                    key TEXT PRIMARY KEY, number TEXT, updated REAL);
                CREATE TABLE IF NOT EXISTS row_state(
                    key TEXT PRIMARY KEY, confirmed INTEGER, memo TEXT, updated REAL);
                """
            )

    def close(self):
        with self._lock:
            self._db.close()

    # --- 読み取り結果 ---
    def get_reading(self, key: str, reader_id: str) -> ReadResult | None:
        with self._lock:
            row = self._db.execute(
                "SELECT json FROM readings WHERE key=? AND reader_id=?", (key, reader_id)
            ).fetchone()
        if not row:
            return None
        try:
            return ReadResult.model_validate_json(row[0])
        except Exception:
            return None  # 壊れたキャッシュは無視して読み直す

    def put_reading(self, key: str, reader_id: str, result: ReadResult) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO readings VALUES(?,?,?,?)",
                (key, reader_id, result.model_dump_json(), time.time()),
            )

    # --- 手修正 ---
    def get_corrections(self) -> dict[str, str]:
        with self._lock:
            return dict(self._db.execute("SELECT key, number FROM corrections").fetchall())

    def set_correction(self, key: str, number: str | None) -> None:
        with self._lock, self._db:
            if number:
                self._db.execute(
                    "INSERT OR REPLACE INTO corrections VALUES(?,?,?)", (key, number, time.time())
                )
            else:
                self._db.execute("DELETE FROM corrections WHERE key=?", (key,))

    # --- 確認済み・メモ ---
    def get_states(self) -> dict[str, tuple[bool, str]]:
        with self._lock:
            rows = self._db.execute("SELECT key, confirmed, memo FROM row_state").fetchall()
        return {k: (bool(c), m or "") for k, c, m in rows}

    def set_state(self, key: str, confirmed: bool, memo: str) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO row_state VALUES(?,?,?,?)",
                (key, int(confirmed), memo, time.time()),
            )
