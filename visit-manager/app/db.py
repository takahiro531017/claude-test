import sqlite3
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS sales_reps (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS stores (
  code TEXT PRIMARY KEY,                 -- 得意先コード(文字列)
  company TEXT NOT NULL,                 -- 得意先名(法人)
  name TEXT NOT NULL DEFAULT '',         -- 店舗名(空欄可)
  rep_code TEXT NOT NULL REFERENCES sales_reps(code),
  active INTEGER NOT NULL DEFAULT 1,     -- マスタから消えたら 0(履歴は残す)
  manual INTEGER NOT NULL DEFAULT 0      -- 1 = 訪問入力で手入力された「リスト外」の訪問先(担当店舗の集計には含めない)
);
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  rep_code TEXT REFERENCES sales_reps(code),
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('sales','admin')),
  must_change INTEGER NOT NULL DEFAULT 1,
  active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS visits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  visit_date TEXT NOT NULL,              -- YYYY-MM-DD (日本時間の日付)
  store_code TEXT NOT NULL REFERENCES stores(code),
  rep_code TEXT NOT NULL REFERENCES sales_reps(code),  -- 訪問した時点の営業
  memo TEXT NOT NULL DEFAULT '',
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_visits_date ON visits(visit_date);
CREATE INDEX IF NOT EXISTS ix_visits_store ON visits(store_code);
CREATE INDEX IF NOT EXISTS ix_visits_rep ON visits(rep_code);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS import_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  imported_at TEXT NOT NULL,
  imported_by TEXT NOT NULL,
  filename TEXT NOT NULL,
  report_json TEXT NOT NULL
);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15, check_same_thread=False)  # 1リクエスト内で順番に使うだけなので安全
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(stores)")]
    if "manual" not in cols:   # 既存のDBを引き継ぐための移行(データは消えません)
        conn.execute("ALTER TABLE stores ADD COLUMN manual INTEGER NOT NULL DEFAULT 0")
    conn.commit()


def get_setting(conn, key: str, default: str) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default
