"""架空のサンプルデータ(実在の企業・個人とは無関係)。初回起動時に自動で入り、sample/ にもCSVを書き出す。"""
import random
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from . import db

CLIENT = "サンプル株式会社(架空)"
ACCOUNT = "sample_cafe_official"
THEMES = ["新商品", "スタッフ紹介", "お客様の声", "豆知識", "キャンペーン", "店内の様子"]
TYPE_BASE = {"リール": 4500, "動画": 2800, "画像": 1900, "ストーリーズ": 900}
TYPE_W = {"画像": 5, "リール": 4, "動画": 2, "ストーリーズ": 3}
THEME_MULT = {"新商品": 1.15, "スタッフ紹介": 0.9, "お客様の声": 1.0, "豆知識": 1.1, "キャンペーン": 1.3, "店内の様子": 0.85}
HOUR_MULT = {8: 0.9, 12: 1.0, 19: 1.15, 21: 1.05}
SAVE_MULT = {"豆知識": 2.2, "新商品": 1.2, "キャンペーン": 0.8}

MONTHS = [(2026, m) for m in range(4, 10)]


def make(seed=42):
    rnd = random.Random(seed)
    posts, snaps = [], []
    followers = 8200
    for i, (y, m) in enumerate(MONTHS):
        start = date(y, m, 1)
        end = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
        month_posts, seen = [], set()
        while len(month_posts) < 14:
            d = start + timedelta(days=rnd.randrange((end - start).days + 1))
            ptype = rnd.choices(list(TYPE_W), weights=list(TYPE_W.values()))[0]
            theme = rnd.choice(THEMES)
            hour = rnd.choice(list(HOUR_MULT))
            if (d, hour, ptype) in seen:  # 同じ日時・種類の重複は作らない
                continue
            seen.add((d, hour, ptype))
            growth = 1 + i * 0.07
            reach = int(TYPE_BASE[ptype] * THEME_MULT[theme] * HOUR_MULT[hour] * growth * rnd.uniform(0.7, 1.3))
            imp = int(reach * rnd.uniform(1.15, 1.6))
            like_r = rnd.uniform(0.03, 0.055) * (1.2 if ptype == "画像" else 1.0)
            save_r = rnd.uniform(0.008, 0.02) * SAVE_MULT.get(theme, 1.0) * (1.4 if ptype == "画像" else 0.8)
            month_posts.append(dict(
                posted_at=datetime(d.year, d.month, d.day, hour, 0).strftime("%Y-%m-%d %H:%M"),
                post_type=ptype, theme=theme, caption="", impressions=imp, reach=reach,
                likes=int(reach * like_r), comments=int(reach * rnd.uniform(0.001, 0.006)),
                saves=int(reach * save_r), shares=int(reach * rnd.uniform(0.002, 0.012)),
                profile_visits=int(reach * rnd.uniform(0.01, 0.03)),
                link_clicks=int(reach * rnd.uniform(0.001, 0.006))))
        posts += month_posts
        tot = lambda k: sum(p[k] for p in month_posts)
        gain = int(tot("reach") * rnd.uniform(0.008, 0.014)) if (y, m) != (2026, 8) else -40
        followers += gain
        snaps.append(dict(period_start=start.isoformat(), period_end=end.isoformat(), account=ACCOUNT, followers=followers,
                          impressions=tot("impressions"), reach=int(tot("reach") * 0.7), likes=tot("likes"),
                          comments=tot("comments"), saves=tot("saves"), shares=tot("shares"),
                          profile_visits=tot("profile_visits"), link_clicks=tot("link_clicks")))
    return snaps, posts


def write_csv(folder: Path):
    snaps, posts = make()
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(snaps).rename(columns=CSV_SNAP).to_csv(folder / "sample_account.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(posts).drop(columns=["caption"]).rename(columns=CSV_POST).to_csv(
        folder / "sample_posts.csv", index=False, encoding="utf-8-sig")


CSV_SNAP = dict(period_start="開始日", period_end="終了日", account="アカウント名", followers="フォロワー数", impressions="インプレッション",
                reach="リーチ", likes="いいね", comments="コメント", saves="保存", shares="シェア",
                profile_visits="プロフィールアクセス", link_clicks="リンククリック")
CSV_POST = dict(posted_at="投稿日時", post_type="投稿タイプ", theme="テーマ", impressions="インプレッション", reach="リーチ",
                likes="いいね", comments="コメント", saves="保存", shares="シェア",
                profile_visits="プロフィールアクセス", link_clicks="リンククリック")


def seed_if_empty():
    db.init_db()
    if len(db.clients_df()):
        return
    with db.connect() as c:
        cid = c.execute("INSERT INTO clients(name, is_sample) VALUES (?,1)", (CLIENT,)).lastrowid
    snaps, posts = make()
    for s in snaps:
        db.save_snapshot(cid, s)
    for p in posts:
        p["account"] = ACCOUNT
        db.save_post(cid, p)
    db.add_meeting(cid, "2026-09-05", "9月はリールを週1本から週2本に増やす。", "豆知識の投稿を月3本つくる。プロフィールのリンクを見直す。")
