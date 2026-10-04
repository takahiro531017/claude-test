"""指標の計算。数字が足りないときは None(=「データなし」)のままにして、推測で埋めない。
日ごとの数字 → 月ごとのまとめ、投稿した日の分析、曜日別などを作る。"""
import calendar

import pandas as pd

from .db import COUNT_COLS, POST_TYPE_COL

WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]
REACT_ALL = ["likes", "comments", "saves", "shares"]
REACT_NAME = {"likes": "いいね", "comments": "コメント", "saves": "保存", "shares": "シェア"}
FEED_TYPES = ["画像", "カルーセル", "リール", "動画"]


def prepare_daily(df: pd.DataFrame) -> pd.DataFrame:
    """日ごとの表に、曜日・投稿した日の目印・反応の合計などを足す。"""
    d = df.copy()
    num = [c for c in d.columns if c not in ("id", "client_id", "sns", "account", "date")]
    for c in num:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["dt"] = pd.to_datetime(d["date"])
    d = d.sort_values("dt").reset_index(drop=True)
    d["month"] = d["dt"].dt.strftime("%Y-%m")
    d["weekday"] = d["dt"].dt.weekday.map(lambda i: WEEKDAYS[i] + "曜日")
    for c in COUNT_COLS:
        d[c] = d[c].fillna(0)
    d["feed_posts"] = d[[POST_TYPE_COL[t] for t in FEED_TYPES]].sum(axis=1)
    d["post_day"] = d["feed_posts"] > 0
    # 反応の合計: データがある種類だけで計算する(例: シェアが無いデータなら いいね+コメント+保存)
    react = [c for c in REACT_ALL if d[c].notna().any()]
    d.attrs["react"] = react
    d["engagement"] = d[react].sum(axis=1, min_count=len(react)) if react else float("nan")
    d["eng_rate"] = d["engagement"] / d["reach"].where(d["reach"] > 0)
    d["link_taps"] = d[["website_taps", "text_link_taps"]].sum(axis=1, min_count=1)
    d["end_followers"] = d["followers"] + d["follower_net"]  # この表のフォロワー数は「その日のはじめ」の人数
    day_types = []
    for _, r in d.iterrows():
        have = [t for t in FEED_TYPES if r[POST_TYPE_COL[t]] > 0]
        day_types.append(None if not have else have[0] if len(have) == 1 else "複数の種類")
    d["day_type"] = day_types
    return d


def _sum(s):
    return float(s.sum()) if s.notna().any() else None


def _pooled(d, num, den):
    ok = d.dropna(subset=[num, den])
    tot = ok[den].sum()
    return float(ok[num].sum() / tot) if len(ok) and tot > 0 else None


def monthly_summary(d: pd.DataFrame) -> pd.DataFrame:
    """日ごと → 月ごとのまとめ。列名は analysis.METRICS のキーに合わせている。"""
    rows = []
    for mkey, g in d.groupby("month"):
        y, m = map(int, mkey.split("-"))
        last = g.iloc[-1]
        fe = last["end_followers"] if pd.notna(last["end_followers"]) else last["followers"]
        rows.append(dict(
            id=mkey, start=pd.Timestamp(y, m, 1), end=pd.Timestamp(y, m, calendar.monthrange(y, m)[1]),
            days=len(g), days_in_month=calendar.monthrange(y, m)[1],
            followers=float(fe) if pd.notna(fe) else None,
            followers_start=float(g.iloc[0]["followers"]) if pd.notna(g.iloc[0]["followers"]) else None,
            follower_gain=_sum(g["follower_net"]),
            impressions=_sum(g["impressions"]), reach=_sum(g["reach"]),
            likes=_sum(g["likes"]), comments=_sum(g["comments"]), saves=_sum(g["saves"]), shares=_sum(g["shares"]),
            engagement=_sum(g["engagement"]), eng_rate=_pooled(g, "engagement", "reach"),
            save_rate=_pooled(g, "saves", "reach"), frequency=_pooled(g, "impressions", "reach"),
            profile_visits=_sum(g["profile_views"]), link_clicks=_sum(g["link_taps"]),
            link_rate=(_sum(g["link_taps"]) / _sum(g["profile_views"])) if _sum(g["profile_views"]) else None,
            post_days=int(g["post_day"].sum()), posts_n=int(g["feed_posts"].sum())))
    S = pd.DataFrame(rows)
    return S


def find_ref(S: pd.DataFrame, idx: int, months=None):
    """比べる相手の月。months=None なら1つ前(前回)。ちょうどその月前のデータが無ければ None。"""
    if months is None:
        return S.iloc[idx - 1] if idx > 0 else None
    cur = S.loc[idx, "start"]
    target = cur - pd.DateOffset(months=months)
    hit = S[S["start"] == target]
    return hit.iloc[0] if len(hit) else None


def week_bins(g: pd.DataFrame):
    """月の中の日を 1〜7日, 8〜14日 ... に区切る。戻り値: [(ラベル, その週の日ごと表)]"""
    out = []
    for k in range(5):
        w = g[((g["dt"].dt.day - 1) // 7) == k]
        if len(w):
            a, b = w["dt"].iloc[0], w["dt"].iloc[-1]
            out.append((f"{a.month}/{a.day}〜{b.month}/{b.day}", w))
    return out


def breakdown(P: pd.DataFrame, col: str, order=None):
    """投稿した日だけを集めて、col ごとに 平均リーチ・エンゲージメント率 を出す。"""
    rows = []
    if P.empty or col not in P:
        return rows
    for k, g in P.dropna(subset=[col]).groupby(col):
        rows.append(dict(key=k, n=len(g), avg_reach=float(g["reach"].mean()) if g["reach"].notna().any() else None,
                         rate=_pooled(g, "engagement", "reach"), save_rate=_pooled(g, "saves", "reach")))
    if order:
        rows.sort(key=lambda r: order.index(r["key"]) if r["key"] in order else 99)
    return rows
