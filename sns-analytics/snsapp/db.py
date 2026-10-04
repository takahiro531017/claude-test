"""SQLite保存。データは data/sns.db に蓄積され、アプリを閉じても残る。クライアントごとに client_id で分けて管理する。"""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SNS = "Instagram"

SNAP_NUM = ["followers", "impressions", "reach", "likes", "comments", "saves", "shares", "profile_visits", "link_clicks"]
POST_NUM = SNAP_NUM[1:]
POST_TYPES = ["画像", "動画", "リール", "ストーリーズ"]


def data_dir() -> Path:
    p = Path(os.environ.get("SNS_DATA_DIR", ROOT / "data"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def output_dir() -> Path:
    p = Path(os.environ.get("SNS_OUTPUT_DIR", ROOT / "output"))
    p.mkdir(parents=True, exist_ok=True)
    return p


@contextmanager
def connect():
    c = sqlite3.connect(data_dir() / "sns.db")
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


SCHEMA = f"""
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, is_sample INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER NOT NULL REFERENCES clients(id),
    sns TEXT NOT NULL, account TEXT NOT NULL, period_start TEXT NOT NULL, period_end TEXT NOT NULL,
    {", ".join(f"{c} REAL" for c in SNAP_NUM)},
    UNIQUE(client_id, sns, account, period_start, period_end));
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER NOT NULL REFERENCES clients(id),
    sns TEXT NOT NULL, account TEXT NOT NULL DEFAULT '', posted_at TEXT NOT NULL, post_type TEXT NOT NULL,
    theme TEXT DEFAULT '', caption TEXT DEFAULT '',
    {", ".join(f"{c} REAL" for c in POST_NUM)},
    UNIQUE(client_id, sns, posted_at, post_type));
CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER NOT NULL REFERENCES clients(id),
    meeting_date TEXT NOT NULL, decided TEXT DEFAULT '', next_actions TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER NOT NULL REFERENCES clients(id),
    created_at TEXT NOT NULL, period_label TEXT, label TEXT, html_path TEXT, pdf_path TEXT, xlsx_path TEXT);
"""


def init_db():
    with connect() as c:
        c.executescript(SCHEMA)


def _df(sql, params=()):
    with connect() as c:
        return pd.read_sql_query(sql, c, params=params)


# ---- クライアント ----
def clients_df():
    return _df("SELECT * FROM clients ORDER BY id")


def add_client(name: str) -> int:
    with connect() as c:
        cur = c.execute("INSERT INTO clients(name) VALUES (?)", (name.strip(),))
        return cur.lastrowid


# ---- 期間ごとの数字 ----
def _nums(rec, cols):
    return [None if rec.get(k) is None or pd.isna(rec.get(k)) else float(rec[k]) for k in cols]


def snapshot_exists(client_id, rec) -> bool:
    with connect() as c:
        r = c.execute("SELECT 1 FROM snapshots WHERE client_id=? AND sns=? AND account=? AND period_start=? AND period_end=?",
                      (client_id, rec.get("sns", SNS), rec["account"], rec["period_start"], rec["period_end"])).fetchone()
    return r is not None


def save_snapshot(client_id, rec, overwrite=False) -> str:
    """'inserted' / 'updated' / 'skipped'。同じ期間が既にあるときは overwrite=True のときだけ上書き。"""
    exists = snapshot_exists(client_id, rec)
    if exists and not overwrite:
        return "skipped"
    cols = ["client_id", "sns", "account", "period_start", "period_end"] + SNAP_NUM
    vals = [client_id, rec.get("sns", SNS), rec["account"], rec["period_start"], rec["period_end"]] + _nums(rec, SNAP_NUM)
    sets = ", ".join(f"{c}=excluded.{c}" for c in SNAP_NUM)
    with connect() as c:
        c.execute(f"INSERT INTO snapshots({','.join(cols)}) VALUES ({','.join('?' * len(cols))}) "
                  f"ON CONFLICT(client_id, sns, account, period_start, period_end) DO UPDATE SET {sets}", vals)
    return "updated" if exists else "inserted"


def snapshots_df(client_id, account=None):
    sql, p = "SELECT * FROM snapshots WHERE client_id=?", [client_id]
    if account:
        sql += " AND account=?"
        p.append(account)
    return _df(sql + " ORDER BY period_end, period_start", p)


def update_snapshot(sid, rec):
    sets = ", ".join(f"{k}=?" for k in ["account", "period_start", "period_end"] + SNAP_NUM)
    with connect() as c:
        c.execute(f"UPDATE snapshots SET {sets} WHERE id=?",
                  [rec["account"], rec["period_start"], rec["period_end"]] + _nums(rec, SNAP_NUM) + [sid])


def delete_rows(table, ids):
    assert table in ("snapshots", "posts", "meetings")
    with connect() as c:
        c.executemany(f"DELETE FROM {table} WHERE id=?", [(int(i),) for i in ids])


# ---- 投稿ごとの数字 ----
def post_exists(client_id, rec) -> bool:
    with connect() as c:
        r = c.execute("SELECT 1 FROM posts WHERE client_id=? AND sns=? AND posted_at=? AND post_type=?",
                      (client_id, rec.get("sns", SNS), rec["posted_at"], rec["post_type"])).fetchone()
    return r is not None


def save_post(client_id, rec, overwrite=False) -> str:
    exists = post_exists(client_id, rec)
    if exists and not overwrite:
        return "skipped"
    cols = ["client_id", "sns", "account", "posted_at", "post_type", "theme", "caption"] + POST_NUM
    vals = [client_id, rec.get("sns", SNS), rec.get("account", ""), rec["posted_at"], rec["post_type"],
            rec.get("theme") or "", rec.get("caption") or ""] + _nums(rec, POST_NUM)
    sets = ", ".join(f"{c}=excluded.{c}" for c in ["account", "theme", "caption"] + POST_NUM)
    with connect() as c:
        c.execute(f"INSERT INTO posts({','.join(cols)}) VALUES ({','.join('?' * len(cols))}) "
                  f"ON CONFLICT(client_id, sns, posted_at, post_type) DO UPDATE SET {sets}", vals)
    return "updated" if exists else "inserted"


def posts_df(client_id):
    return _df("SELECT * FROM posts WHERE client_id=? ORDER BY posted_at", [client_id])


def update_post(pid, rec):
    keys = ["posted_at", "post_type", "theme", "caption"] + POST_NUM
    with connect() as c:
        c.execute(f"UPDATE posts SET {', '.join(f'{k}=?' for k in keys)} WHERE id=?",
                  [rec["posted_at"], rec["post_type"], rec.get("theme") or "", rec.get("caption") or ""]
                  + _nums(rec, POST_NUM) + [pid])


# ---- 会議メモ ----
def add_meeting(client_id, meeting_date, decided, next_actions):
    with connect() as c:
        c.execute("INSERT INTO meetings(client_id, meeting_date, decided, next_actions) VALUES (?,?,?,?)",
                  (client_id, meeting_date, decided, next_actions))


def meetings_df(client_id):
    return _df("SELECT * FROM meetings WHERE client_id=? ORDER BY meeting_date, id", [client_id])


def update_meeting(mid, meeting_date, decided, next_actions):
    with connect() as c:
        c.execute("UPDATE meetings SET meeting_date=?, decided=?, next_actions=? WHERE id=?",
                  (meeting_date, decided, next_actions, mid))


# ---- 分析ファイルの履歴 ----
def add_report(client_id, created_at, period_label, label, html_path, pdf_path, xlsx_path):
    with connect() as c:
        c.execute("INSERT INTO reports(client_id, created_at, period_label, label, html_path, pdf_path, xlsx_path) "
                  "VALUES (?,?,?,?,?,?,?)", (client_id, created_at, period_label, label, html_path, pdf_path, xlsx_path))


def reports_df(client_id):
    return _df("SELECT * FROM reports WHERE client_id=? ORDER BY id DESC", [client_id])


def diff_edits(original: pd.DataFrame, edited: pd.DataFrame):
    """表の編集結果を比べる。戻り値: (内容が変わった行のリスト, 削除にチェックされたidのリスト)"""
    dels = edited.loc[edited["削除"].astype(bool), "id"].astype(int).tolist()
    changed = []
    for (_, a), (_, b) in zip(original.iterrows(), edited.iterrows()):
        if not bool(b["削除"]) and not a.drop("削除").equals(b.drop("削除")):
            changed.append(b)
    return changed, dels
