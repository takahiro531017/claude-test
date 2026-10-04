"""指標の計算。数字が足りないときは None(=「データなし」)のままにして、推測で埋めない。"""
from datetime import timedelta

import pandas as pd

REACT = ["likes", "comments", "saves", "shares"]
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]
BUCKETS = [("深夜(0〜5時)", 0, 6), ("朝(6〜10時)", 6, 11), ("昼(11〜14時)", 11, 15), ("夕方(15〜18時)", 15, 19), ("夜(19〜23時)", 19, 24)]


def _ratio(a, b):
    return a / b.where(b > 0)


def add_rates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in ["impressions", "reach", "profile_visits", "link_clicks", "followers"] + REACT:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["engagement"] = df[REACT].sum(axis=1, min_count=len(REACT))  # 1つでも欠けていたら「データなし」
    df["eng_rate"] = _ratio(df["engagement"], df["reach"])
    df["save_rate"] = _ratio(df["saves"], df["reach"])
    df["profile_rate"] = _ratio(df["profile_visits"], df["reach"])
    df["link_rate"] = _ratio(df["link_clicks"], df["profile_visits"])
    df["frequency"] = _ratio(df["impressions"], df["reach"])
    return df


def prepare_snapshots(df: pd.DataFrame) -> pd.DataFrame:
    df = add_rates(df).sort_values(["period_end", "period_start"]).reset_index(drop=True)
    df["start"] = pd.to_datetime(df["period_start"])
    df["end"] = pd.to_datetime(df["period_end"])
    df["follower_gain"] = df["followers"].diff()
    return df


def prepare_posts(df: pd.DataFrame) -> pd.DataFrame:
    df = add_rates(df)
    df["dt"] = pd.to_datetime(df["posted_at"], errors="coerce")
    df["has_time"] = df["posted_at"].astype(str).str.len() > 10
    df["weekday"] = df["dt"].dt.weekday.map(lambda i: None if pd.isna(i) else WEEKDAYS[int(i)] + "曜日")
    df["bucket"] = [None if not ht or pd.isna(d) else next(n for n, a, b in BUCKETS if a <= d.hour < b)
                    for d, ht in zip(df["dt"], df["has_time"])]
    return df.sort_values("dt").reset_index(drop=True)


def period_posts(posts: pd.DataFrame, start, end) -> pd.DataFrame:
    if posts.empty:
        return posts
    d = posts["dt"].dt.normalize()
    return posts[(d >= pd.Timestamp(start)) & (d <= pd.Timestamp(end))].reset_index(drop=True)


def find_ref(df: pd.DataFrame, idx: int, days=None, tol=0):
    """比べる相手の行を返す。days=None なら1つ前(前回)。見つからなければ None。"""
    if days is None:
        return df.iloc[idx - 1] if idx > 0 else None
    target = df.loc[idx, "end"] - timedelta(days=days)
    cand = df[df.index < idx].copy()
    if cand.empty:
        return None
    cand["gap"] = (cand["end"] - target).abs().dt.days
    best = cand.sort_values("gap").iloc[0]
    return best if best["gap"] <= tol else None


def pooled_rate(d: pd.DataFrame, num: str, den: str):
    ok = d.dropna(subset=[num, den])
    s = ok[den].sum()
    return float(ok[num].sum() / s) if len(ok) and s > 0 else None


def breakdown(posts: pd.DataFrame, col: str, order=None):
    rows = []
    if posts.empty or col not in posts:
        return rows
    for k, d in posts.dropna(subset=[col]).groupby(col):
        rows.append(dict(key=k, n=len(d), avg_reach=float(d["reach"].mean()) if d["reach"].notna().any() else None,
                         rate=pooled_rate(d, "engagement", "reach"), save_rate=pooled_rate(d, "saves", "reach")))
    if order:
        rows.sort(key=lambda r: order.index(r["key"]) if r["key"] in order else 99)
    return rows
