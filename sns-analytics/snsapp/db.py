"""SQLite保存。データは data/sns.db に蓄積され、アプリを閉じても残る。クライアントごとに client_id で分けて管理する。
1行 = 1日(daily)。月ごとの数字は、保存した日ごとの数字から集計して作る。"""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SNS = "Instagram"

# 日ごとの数字の列(DB列名, 画面の名前, 入力の例, 意味)
DAILY_FIELDS = [
    ("followers", "フォロワー数", "例: 2202", "その日のはじめのフォロワーの人数"),
    ("follower_net", "フォロワー増減", "例: 69", "その日に増えた人数(新規−解除。減った日はマイナス)"),
    ("new_followers", "新規フォロワー数", "例: 97", "その日に新しくフォローした人数"),
    ("follows", "フォロー数", "例: 6", "このアカウントがフォローしている数"),
    ("follows_change", "フォロー増減", "例: 0", "フォロー数の増減"),
    ("impressions", "インプレッション", "例: 12788", "その日に投稿した分が画面に表示された回数"),
    ("reach", "リーチ", "例: 5510", "その日に投稿した分を見た人の数"),
    ("likes", "いいね", "例: 1520", "いいねの回数"),
    ("comments", "コメント", "例: 12", "コメントの数"),
    ("saves", "保存", "例: 212", "保存された回数"),
    ("shares", "シェア", "例: 30", "シェアされた回数"),
    ("video_views", "動画再生", "例: 313", "動画・リールが再生された回数"),
    ("profile_views", "プロフィールアクセス", "例: 396", "プロフィール画面が開かれた回数"),
    ("website_taps", "ウェブサイトタップ", "例: 8", "プロフィールのウェブサイトのリンクが押された回数"),
    ("text_link_taps", "テキスト内リンクタップ", "例: 0", "プロフィール文の中のリンクが押された回数"),
    ("email_taps", "メールタップ", "例: 0", "メールボタンが押された回数"),
    ("phone_taps", "電話番号タップ", "例: 0", "電話ボタンが押された回数"),
    ("direction_taps", "道順タップ", "例: 0", "道順(地図)ボタンが押された回数"),
    ("posts_image", "画像の投稿数", "例: 0", "その日に投稿した画像の本数"),
    ("posts_carousel", "カルーセルの投稿数", "例: 2", "その日に投稿したカルーセル(複数枚の画像)の本数"),
    ("posts_reel", "リールの投稿数", "例: 1", "その日に投稿したリール(短い縦型動画)の本数"),
    ("posts_video", "動画の投稿数", "例: 0", "その日に投稿した動画の本数"),
    ("posts_story", "ストーリーズの投稿数", "例: 1", "その日に投稿したストーリーズの本数"),
]
DAILY_COLS = [f[0] for f in DAILY_FIELDS]
DAILY_LABEL = {f[0]: f[1] for f in DAILY_FIELDS}
COUNT_COLS = ["posts_image", "posts_carousel", "posts_reel", "posts_video", "posts_story"]  # 空欄は 0 本として扱う
POST_TYPE_COL = {"画像": "posts_image", "カルーセル": "posts_carousel", "リール": "posts_reel", "動画": "posts_video", "ストーリーズ": "posts_story"}


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
CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER NOT NULL REFERENCES clients(id),
    sns TEXT NOT NULL, account TEXT NOT NULL, date TEXT NOT NULL,
    {", ".join(f"{c} REAL" for c in DAILY_COLS)},
    UNIQUE(client_id, sns, account, date));
CREATE TABLE IF NOT EXISTS demographics (
    id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER NOT NULL REFERENCES clients(id),
    sns TEXT NOT NULL, account TEXT NOT NULL, period_start TEXT NOT NULL, period_end TEXT NOT NULL,
    kind TEXT NOT NULL, grp TEXT NOT NULL, female_pct REAL, female_n REAL, male_pct REAL, male_n REAL);
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


def _num(v):
    return None if v is None or pd.isna(v) else float(v)


# ---- クライアント ----
def clients_df():
    return _df("SELECT * FROM clients ORDER BY id")


def add_client(name: str) -> int:
    with connect() as c:
        return c.execute("INSERT INTO clients(name) VALUES (?)", (name.strip(),)).lastrowid


def get_or_add_client(name: str) -> int:
    df = clients_df()
    hit = df[df["name"] == name.strip()]
    return int(hit["id"].iloc[0]) if len(hit) else add_client(name)


# ---- 日ごとの数字 ----
def upsert_daily(client_id, account, rows, overwrite=False, sns=SNS):
    """rows: [{'date': 'YYYY-MM-DD', 列名: 数字 or None, ...}]。
    overwrite=False: 既にある数字は変えず、空欄だけ埋める。 True: ファイルの数字で上書き(ファイルが空欄の所は今の数字を残す)。
    戻り値: dict(inserted=新しい日の数, updated=数字が変わった日の数, unchanged=変化なしの日の数)"""
    res = dict(inserted=0, updated=0, unchanged=0)
    with connect() as c:
        for r in rows:
            cur = c.execute("SELECT * FROM daily WHERE client_id=? AND sns=? AND account=? AND date=?",
                            (client_id, sns, account, r["date"])).fetchone()
            new = {k: _num(r.get(k)) for k in DAILY_COLS if k in r}
            if cur is None:
                cols = ["client_id", "sns", "account", "date"] + list(new)
                c.execute(f"INSERT INTO daily({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                          [client_id, sns, account, r["date"]] + list(new.values()))
                res["inserted"] += 1
                continue
            upd = {}
            for k, v in new.items():
                if v is None:
                    continue
                if cur[k] is None or (overwrite and cur[k] != v):
                    upd[k] = v
            if upd:
                c.execute(f"UPDATE daily SET {', '.join(f'{k}=?' for k in upd)} WHERE id=?", list(upd.values()) + [cur["id"]])
                res["updated"] += 1
            else:
                res["unchanged"] += 1
    return res


def daily_df(client_id, account=None):
    sql, p = "SELECT * FROM daily WHERE client_id=?", [client_id]
    if account:
        sql += " AND account=?"
        p.append(account)
    return _df(sql + " ORDER BY date", p)


def update_daily(did, rec):
    keys = ["date"] + DAILY_COLS
    with connect() as c:
        c.execute(f"UPDATE daily SET {', '.join(f'{k}=?' for k in keys)} WHERE id=?",
                  [rec["date"]] + [_num(rec.get(k)) for k in DAILY_COLS] + [did])


def delete_rows(table, ids):
    assert table in ("daily", "demographics", "meetings")
    with connect() as c:
        c.executemany(f"DELETE FROM {table} WHERE id=?", [(int(i),) for i in ids])


# ---- フォロワーの属性(年齢・性別) ----
def demographics_exist(client_id, account, kind, period_start, period_end) -> bool:
    with connect() as c:
        return c.execute("SELECT 1 FROM demographics WHERE client_id=? AND account=? AND kind=? AND period_start=? AND period_end=?",
                         (client_id, account, kind, period_start, period_end)).fetchone() is not None


def save_demographics(client_id, account, kind, period_start, period_end, rows, overwrite=False) -> str:
    """同じ期間・同じ種類は、overwrite=True のときだけ入れ替える。'inserted' / 'updated' / 'skipped'"""
    exists = demographics_exist(client_id, account, kind, period_start, period_end)
    if exists and not overwrite:
        return "skipped"
    with connect() as c:
        c.execute("DELETE FROM demographics WHERE client_id=? AND account=? AND kind=? AND period_start=? AND period_end=?",
                  (client_id, account, kind, period_start, period_end))
        for r in rows:
            c.execute("INSERT INTO demographics(client_id, sns, account, period_start, period_end, kind, grp, female_pct, female_n, male_pct, male_n) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (client_id, SNS, account, period_start, period_end, kind, r["grp"], _num(r.get("female_pct")),
                       _num(r.get("female_n")), _num(r.get("male_pct")), _num(r.get("male_n"))))
    return "updated" if exists else "inserted"


def demographics_df(client_id, account=None):
    sql, p = "SELECT * FROM demographics WHERE client_id=?", [client_id]
    if account:
        sql += " AND account=?"
        p.append(account)
    return _df(sql + " ORDER BY period_end, kind, id", p)


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
