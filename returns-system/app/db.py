"""SQLite接続とテーブル定義。DBは data/returns.sqlite3 の1ファイル。"""
import contextlib
import sqlite3
from datetime import datetime
from pathlib import Path

from . import config
from .normalize import norm_key

SIMPLE_MASTER_COLS = """
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    note TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    is_reviewed INTEGER NOT NULL DEFAULT 0,
    use_count INTEGER NOT NULL DEFAULT 0,
    last_used_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
"""

SCHEMA_V1 = f"""
CREATE TABLE makers ({SIMPLE_MASTER_COLS});
CREATE TABLE customers ({SIMPLE_MASTER_COLS});
CREATE TABLE defect_types ({SIMPLE_MASTER_COLS}, sort_order INTEGER NOT NULL DEFAULT 0);
CREATE TABLE staff ({SIMPLE_MASTER_COLS});

CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    part_no TEXT NOT NULL,
    part_no_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '',
    name_key TEXT NOT NULL DEFAULT '',
    maker_id INTEGER REFERENCES makers(id),
    note TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    is_reviewed INTEGER NOT NULL DEFAULT 0,
    name_conflict INTEGER NOT NULL DEFAULT 0,
    use_count INTEGER NOT NULL DEFAULT 0,
    last_used_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 統合したマスタの旧表記 → 統合先。今後その表記が入力されても統合先に解決する
CREATE TABLE master_aliases (
    kind TEXT NOT NULL,
    alias_key TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    PRIMARY KEY (kind, alias_key)
);

CREATE TABLE receipt_counters (
    date_key TEXT PRIMARY KEY,
    last_seq INTEGER NOT NULL
);

CREATE TABLE returns (
    id INTEGER PRIMARY KEY,
    receipt_no TEXT NOT NULL UNIQUE,
    received_on TEXT NOT NULL,
    staff_id INTEGER REFERENCES staff(id),
    customer_id INTEGER REFERENCES customers(id),
    product_id INTEGER REFERENCES products(id),
    part_no_text TEXT NOT NULL,
    product_name_text TEXT NOT NULL DEFAULT '',
    maker_id INTEGER REFERENCES makers(id),
    serial_no TEXT NOT NULL DEFAULT '',
    quantity INTEGER NOT NULL DEFAULT 1,
    defect_type_id INTEGER REFERENCES defect_types(id),
    defect_text TEXT NOT NULL DEFAULT '',
    reason_note TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'received',
    disposition TEXT,
    print_status TEXT NOT NULL DEFAULT 'unprinted',
    printed_at TEXT,
    print_count INTEGER NOT NULL DEFAULT 0,
    status_changed_at TEXT NOT NULL,
    closed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_returns_status ON returns(status);
CREATE INDEX idx_returns_received_on ON returns(received_on);
CREATE INDEX idx_returns_product ON returns(product_id);
CREATE INDEX idx_returns_maker ON returns(maker_id);

CREATE TABLE return_photos (
    id INTEGER PRIMARY KEY,
    return_id INTEGER NOT NULL REFERENCES returns(id),
    file_path TEXT NOT NULL,
    thumb_path TEXT NOT NULL,
    taken_at TEXT NOT NULL
);

CREATE TABLE return_events (
    id INTEGER PRIMARY KEY,
    return_id INTEGER NOT NULL REFERENCES returns(id),
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    from_value TEXT,
    to_value TEXT,
    note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_events_return ON return_events(return_id);

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

MIGRATIONS = [SCHEMA_V1]  # 以後のフェーズでここに追加していく

DEFAULT_DEFECTS = [
    "電源が入らない", "動作しない", "異音がする", "破損", "外観キズ", "部品欠品", "水濡れ", "初期不良",
]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or config.db_path()), timeout=30, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextlib.contextmanager
def tx(conn: sqlite3.Connection):
    """書き込みトランザクション(同時登録でも採番が重ならない)。"""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def init_db(conn: sqlite3.Connection) -> None:
    """DBを最新の構造にする。空なら作成し、不良内容の初期候補を入れる。"""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for i, script in enumerate(MIGRATIONS[version:], start=version):
        conn.executescript("BEGIN;" + script + f"PRAGMA user_version={i + 1};COMMIT;")
        if i == 0:
            ts = now_iso()
            for n, name in enumerate(DEFAULT_DEFECTS):
                conn.execute(
                    "INSERT INTO defect_types(name,name_key,sort_order,is_reviewed,created_at,updated_at)"
                    " VALUES(?,?,?,1,?,?)",
                    (name, norm_key(name), n, ts, ts),
                )


def get_setting(conn, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default
