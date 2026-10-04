"""分析の中身づくり。画面・HTML・PDF・Excelはすべてここで作った dict を使う。
文章は数字から機械的に作り、断定せず「〜かもしれません」と書く。データが足りない項目は「データなし」。"""
from datetime import datetime

import pandas as pd

from . import charts as ch
from . import metrics as m
from .glossary import GLOSSARY, t

ND = "データなし"

# (キー, 表示名, 種類) 種類: count=回数・人数 / rate=割合 / delta=増減の人数
METRICS = [
    ("followers", "フォロワー数", "count"), ("follower_gain", "フォロワー増加数", "delta"),
    ("impressions", "インプレッション", "count"), ("reach", "リーチ", "count"), ("eng_rate", "エンゲージメント率", "rate"),
    ("likes", "いいね", "count"), ("comments", "コメント", "count"), ("saves", "保存", "count"), ("shares", "シェア", "count"),
    ("profile_visits", "プロフィールアクセス", "count"), ("link_clicks", "リンククリック", "count"),
]
SHORT = {"followers": "フォローしている人の数(月末)", "follower_gain": "期間中に増えた人数(新規−解除)",
         "impressions": "画面に表示された回数", "reach": "見た「人」の数", "eng_rate": "見た人のうち反応した人の割合",
         "likes": "いいねの回数", "comments": "コメントの数", "saves": "あとで見返すため保存された回数",
         "shares": "友だちに送られた回数", "profile_visits": "プロフィール画面を開いた回数",
         "link_clicks": "プロフィールのリンクを押した回数"}
FLAT = 0.02  # ±2%以内は「ほぼ同じ」


def fmt(v, kind="count"):
    if v is None or pd.isna(v):
        return ND
    return {"count": f"{v:,.0f}", "rate": f"{v * 100:.2f}%", "delta": f"{v:+,.0f}"}[kind]


def val(row, key):
    if row is None:
        return None
    v = row[key]
    return None if pd.isna(v) else float(v)


def change(cur, ref, kind="count"):
    """今回と比べる相手の差を、矢印・色つきの文章にする。"""
    if cur is None or ref is None:
        return dict(text=ND, arrow="–", cls="nodata", pct=None, diff=None)
    diff = cur - ref
    pct = diff / abs(ref) if ref else None
    flat = (diff == 0) if kind == "delta" else ((abs(pct) < FLAT) if pct is not None else diff == 0)
    arrow = "→" if flat else ("↑" if diff > 0 else "↓")
    cls = "flat" if flat else ("up" if diff > 0 else "down")
    if kind == "rate":
        text = f"{arrow} {diff * 100:+.2f}pt"
    elif kind == "delta":
        text = f"{arrow} {diff:+,.0f}人"
    else:
        text = f"{arrow} {diff:+,.0f}" + (f"({pct:+.1%})" if pct is not None else "")
    return dict(text=text, arrow=arrow, cls=cls, pct=pct, diff=diff)


def md(ts):
    return f"{ts.month}/{ts.day}"


def mdw(ts):
    return f"{ts.month}/{ts.day}({m.WEEKDAYS[ts.weekday()]})"


def month_label(row):
    return f"{row['start'].month}月"


def period_text(row):
    return f"{row['start']:%Y/%m/%d}〜{row['end']:%Y/%m/%d}"


def share_of_top(g, col):
    """col の合計のうち、いちばん多い1日が占める割合。(日付, 割合, 合計)"""
    s = g[col].dropna()
    if s.empty or s.sum() <= 0:
        return None
    i = s.idxmax()
    return g.loc[i, "dt"], float(s.max() / s.sum()), float(s.sum())


# ---------- 投稿した日ごとの分析 ----------
def day_view(r):
    n = int(r["feed_posts"])
    return dict(date=mdw(r["dt"]), type=f"{r['day_type']} {n}本", reach=fmt(val(r, "reach")), impressions=fmt(val(r, "impressions")),
                rate=fmt(val(r, "eng_rate"), "rate"), saves=fmt(val(r, "saves")), likes=fmt(val(r, "likes")), comments=fmt(val(r, "comments")))


def post_factors(p, P):
    """この日の数字が、全体平均よりどれだけ違うかを理由の候補として並べる(差が大きい順)。"""
    overall = m._pooled(P, "engagement", "reach")
    out = []
    if overall:
        for col, label in [("day_type", "投稿の種類"), ("weekday", "曜日")]:
            k = p.get(col)
            if k is None or pd.isna(k):
                continue
            g = P[P[col] == k]
            rate = m._pooled(g, "engagement", "reach")
            if len(g) >= 2 and rate is not None:
                dev = rate / overall - 1
                out.append((dev, f"同じ{label}「{k}」の日({len(g)}日)は、全体より{t('エンゲージメント率')}が{abs(dev):.0%}"
                                 f"{'高い' if dev > 0 else '低い'}傾向があります"))
    sr, osr = p.get("saves"), m._pooled(P, "saves", "reach")
    if pd.notna(sr) and pd.notna(p.get("reach")) and p["reach"] > 0 and osr:
        r_ = sr / p["reach"]
        dev = r_ / osr - 1
        out.append((dev, f"この日の{t('保存率')}は{r_:.2%}で、全体の{osr:.2%}より{abs(dev):.0%}{'高く' if dev > 0 else '低く'}なっています"))
    avg = P["reach"].mean()
    if pd.notna(p.get("reach")) and avg:
        dev = p["reach"] / avg - 1
        out.append((dev, f"この日の{t('リーチ')}は{p['reach']:,.0f}で、全体の平均{avg:,.0f}より{abs(dev):.0%}{'多く' if dev > 0 else '少なく'}なっています"))
    cs = P["comments"].sum() if "comments" in P and P["comments"].notna().any() else 0
    if cs and pd.notna(p.get("comments")) and p["comments"] / cs >= 0.5:
        out.append((9.9, f"今月の{t('コメント')}の{p['comments'] / cs:.0%}がこの日に集まっています(特別な企画や呼びかけがあった可能性があります)"))
    return out


def hypothesis(p, P, good):
    f = [x for x in post_factors(p, P) if abs(x[0]) >= 0.1 and (x[0] > 0) == good]
    f.sort(key=lambda x: -abs(x[0]))
    if not f:
        return "はっきりした理由は、今ある数字からは見つかりませんでした(データ不足)。"
    return "。".join(s for _, s in f[:2]) + "。そのため、これが理由かもしれません(仮説です)。"


def posts_section(P):
    if P.empty:
        return dict(ok=False, note=f"この期間に投稿した日の数字は{ND}です。")
    R = P.dropna(subset=["eng_rate"]).sort_values("eng_rate", ascending=False)
    if len(R) < 2:
        return dict(ok=False, note=f"{t('エンゲージメント率')}を計算できる投稿した日が足りないため、{ND}です。")
    top = R.head(3)
    worst = R.drop(top.index).tail(3).iloc[::-1] if len(R) > 3 else R.iloc[0:0]
    return dict(ok=True, note="", n=len(P),
                top=[dict(**day_view(r), why=hypothesis(r, P, True)) for _, r in top.iterrows()],
                worst=[dict(**day_view(r), why=hypothesis(r, P, False)) for _, r in worst.iterrows()])


def breakdown_block(P, col, title, order=None):
    rows = m.breakdown(P, col, order)
    if len(rows) < 1:
        return dict(title=title, ok=False, note=f"{title}の比較に使えるデータは{ND}です"
                    + ("(投稿の時刻が、このデータには入っていません)" if col == "bucket" else "") + "。")
    labels = [f"{r['key']}({r['n']}日)" for r in rows]
    rate = ch.bar_chart(labels, [r["rate"] for r in rows], ch.fmt_pct, f"{title}のエンゲージメント率")
    reach = ch.bar_chart(labels, [r["avg_reach"] for r in rows], ch.fmt_int, f"{title}の平均リーチ")
    valid = [r for r in rows if r["rate"] is not None]
    if len(valid) >= 2:
        b, w = max(valid, key=lambda r: r["rate"]), min(valid, key=lambda r: r["rate"])
        cm = (f"→ 「{b['key']}」の{t('エンゲージメント率')}が{b['rate']:.2%}でいちばん高く、「{w['key']}」が{w['rate']:.2%}で最も低いです。"
              + ("ただし日数が少ない(5日未満)グループがあるため、参考程度に見てください。" if min(r["n"] for r in valid) < 5 else ""))
    else:
        cm = f"→ 比べられるグループが1つだけのため、良し悪しの比較は{ND}です。"
    return dict(title=title, ok=True, rate_svg=rate, reach_svg=reach, comment=cm, rows=rows)


def trend_comment(label, c, up_msg, down_msg, flat_msg=None, ref_name="前回"):
    if c["cls"] == "nodata":
        return f"→ {ref_name}のデータがないため、{label}の変化は{ND}です。"
    if c["cls"] == "flat":
        return f"→ {label}は{ref_name}とほぼ同じです。" + (flat_msg or "")
    return f"→ {ref_name}より{label}が{'増えています' if c['cls'] == 'up' else '減っています'}。" + (up_msg if c["cls"] == "up" else down_msg)


def _longest_gap(G):
    pd_ = G.loc[G["post_day"], "dt"].tolist()
    best = None
    for a, b in zip(pd_, pd_[1:]):
        gap = (b - a).days - 1
        if gap > 0 and (best is None or gap > best[0]):
            best = (gap, a, b)
    return best


# ---------- 組み立て ----------
def build_analysis(client_name, daily_raw, demo_raw, meetings, cur_id=None, account=""):
    D = m.prepare_daily(daily_raw)
    if D.empty:
        return None
    S = m.monthly_summary(D)
    idx = len(S) - 1 if cur_id is None else int(S.index[S["id"] == cur_id][0])
    cur = S.iloc[idx]
    G = D[D["month"] == cur["id"]].reset_index(drop=True)
    react = D.attrs.get("react", [])
    PD = G[G["post_day"] & G["reach"].notna() & G["eng_rate"].notna()].reset_index(drop=True)
    cands = []  # (優先度, タイトル, 理由, やり方)
    notes = []

    refs = [("前回", m.find_ref(S, idx)), ("1か月前", m.find_ref(S, idx, 1)), ("3か月前", m.find_ref(S, idx, 3))]
    prev = refs[0][1]
    days = int(cur["days"])
    dlabels = [md(x) for x in G["dt"]]

    # --- 数字の変化 ---
    changes = []
    for key, name, kind in METRICS:
        cv = val(cur, key)
        cells = []
        for rn, r in refs:
            c = change(cv, val(r, key), kind)
            c["ref"] = fmt(val(r, key), kind) if r is not None else ND
            c["ref_name"] = rn
            cells.append(c)
        changes.append(dict(key=key, label=name, short=SHORT[key], current=fmt(cv, kind), cells=cells))
    C = {r["key"]: r["cells"][0] for r in changes}

    gain, fol_end, fol_start = val(cur, "follower_gain"), val(cur, "followers"), val(cur, "followers_start")
    first = G["follower_net"].iloc[:15].mean() if len(G) >= 10 else None
    second = G["follower_net"].iloc[15:].mean() if len(G) >= 20 else None

    # --- まとめ3行 ---
    cmp_f = f"前回より {C['followers']['text']}。" if C["followers"]["cls"] != "nodata" else f"前回(先月)のデータがないため、前回との比較は{ND}です。"
    s1 = (f"フォロワー数は月初 {fmt(fol_start)}人 → 月末 {fmt(fol_end)}人。この月は {fmt(gain, 'delta')}人 増えました"
          f"(1日平均 {gain / days:+,.0f}人)。{cmp_f}") if gain is not None and fol_end is not None and fol_start is not None else f"フォロワー数は{ND}です。"
    top_imp = share_of_top(G, "impressions")
    s2 = (f"{t('リーチ')}は投稿した日の合計で {fmt(val(cur, 'reach'))}人、{t('エンゲージメント率')}は {fmt(val(cur, 'eng_rate'), 'rate')}。"
          + (f"{mdw(top_imp[0])}の投稿だけで、見られた回数の {top_imp[1]:.0%} を占めています。" if top_imp and top_imp[1] >= 0.5 else "")
          ) if val(cur, "reach") is not None else f"リーチ・エンゲージメント率は{ND}です。"
    lr = val(cur, "link_rate")
    s3 = (f"{t('プロフィールアクセス')}は {fmt(val(cur, 'profile_visits'))}回、{t('リンククリック')}は {fmt(val(cur, 'link_clicks'))}回"
          + (f"(プロフィールを開いた100回のうち約{lr * 100:.1f}回)" if lr is not None else "") + "。") if val(cur, "profile_visits") is not None else f"プロフィールの数字は{ND}です。"
    summary = [s1, s2, s3]

    # ======== 1) フォロワー ========
    fol_hyp = []
    if first is not None and second is not None:
        fol_hyp.append(f"1〜15日は1日平均 {first:+,.0f}人、16日以降は {second:+,.0f}人です。"
                       + ("月のはじめに大きく増え、その後はゆるやかになっています。公開や告知の直後に見られる動きかもしれません(仮説)。" if second < first * 0.8
                          else "月の後半のほうが増えるペースが上がっています。" if second > first * 1.2 else "増えるペースはほぼ一定です。"))
        if second < first * 0.8:
            cands.append((85, "増えるペースを保つために、告知・投稿の流れをつくる",
                          f"{t('フォロワー増加数')}が、1〜15日は1日平均 {first:+,.0f}人、16日以降は {second:+,.0f}人と、ペースが落ちています。",
                          "フォローしたくなる理由(プロフィールの一言・固定投稿)を整え、見つけてもらえる投稿(新しい人に届く形式)を定期的に出しましょう。"))
    pdays, ndays = G[G["post_day"]]["follower_net"], G[~G["post_day"]]["follower_net"]
    if len(pdays.dropna()) >= 2 and len(ndays.dropna()) >= 2:
        a, b = pdays.mean(), ndays.mean()
        fol_hyp.append(f"投稿した日の増加は1日平均 {a:+,.0f}人、投稿しなかった日は {b:+,.0f}人です。"
                       + ("投稿した日のほうが増えやすい傾向があります。" if a > b * 1.15 else "投稿の有無で、はっきりした差は見られません。")
                       + "(月のはじめに増加が集中しているため、時期の影響もあります。参考程度に見てください)")
    if not fol_hyp:
        fol_hyp = [f"理由を考えるための数字が足りないため、{ND}です。"]
    best_day = G.loc[G["follower_net"].idxmax()] if G["follower_net"].notna().any() else None
    wk = m.week_bins(G)
    wk_gain = [None if not w["follower_net"].notna().any() else float(w["follower_net"].sum()) for _, w in wk]
    fol_charts = [
        dict(title="フォロワー数の推移(日ごと・その日の終わり)",
             svg=ch.line_chart(dlabels, [("フォロワー数", [None if pd.isna(v) else float(v) for v in G["end_followers"]])], ch.fmt_int, "フォロワー数の推移"),
             comment=(f"→ 月初 {fmt(fol_start)}人から月末 {fmt(fol_end)}人へ、右肩上がりで増えています。" if gain and gain > 0
                      else f"→ 月の間にフォロワーは {fmt(gain, 'delta')}人 の変化でした。")),
        dict(title="週ごとに増えた人数", svg=ch.bar_chart([w[0] for w in wk], wk_gain, lambda v: ND if v is None else f"{v:+,.0f}人", "週ごとのフォロワー増加数"),
             comment=(f"→ 最も増えたのは {wk[wk_gain.index(max(v for v in wk_gain if v is not None))][0]} の週です。" if any(v is not None for v in wk_gain) else f"→ {ND}"))]
    if len(S) >= 2:
        fol_charts.append(dict(title="月ごとのフォロワー数", svg=ch.line_chart([month_label(r) for _, r in S.iterrows()], [("フォロワー数", [val(r, "followers") for _, r in S.iterrows()])], ch.fmt_int, "月ごとのフォロワー数"),
                               comment=trend_comment("フォロワー数", C["followers"], "応援してくれる人が増えています。", "増える勢いが弱まっている可能性があります。")))
    deep_fol = dict(
        key="followers", title="フォロワーの増え方", icon="👥", terms=["フォロワー数", "フォロワー増加数", "前回比"],
        reading=[f"月末のフォロワー数は {fmt(fol_end)}人。この月に {fmt(gain, 'delta')}人 増えました。"
                 + (f"いちばん増えた日は {mdw(best_day['dt'])} の {best_day['follower_net']:+,.0f}人です。" if best_day is not None else "")],
        charts=fol_charts, hypotheses=fol_hyp)
    follower_chart = fol_charts[0]

    # ======== 2) エンゲージメント率 ========
    er_hyp = []
    for col, nm in [("comments", "コメント"), ("likes", "いいね"), ("saves", "保存")]:
        sh = share_of_top(G, col)
        if sh and sh[1] >= 0.5 and sh[2] >= 20:
            er_hyp.append(f"今月の{t(nm)} {sh[2]:,.0f}のうち {sh[1]:.0%} が、{mdw(sh[0])}の1日に集まっています。")
            if col == "comments":
                er_hyp.append("コメントが1日に集中しているのは、プレゼント企画や質問の呼びかけなど、コメントを促す内容だったからかもしれません(仮説。投稿の中身を確認してください)。")
    if len(PD) >= 3:
        topd = PD.loc[PD["engagement"].idxmax()]
        rest = PD.drop(topd.name)
        r2 = m._pooled(rest, "engagement", "reach")
        if r2 is not None and topd["engagement"] / PD["engagement"].sum() >= 0.4:
            er_hyp.append(f"{mdw(topd['dt'])}を除くと、{t('エンゲージメント率')}は {fmt(m._pooled(PD, 'engagement', 'reach'), 'rate')} → {r2 * 100:.2f}% になります。"
                          "特別な1日が全体の数字を大きく引き上げています。")
            cands.append((80, "反応が集まった日の投稿を分析して、同じ型をくり返す",
                          f"{mdw(topd['dt'])}の投稿が、今月の反応の {topd['engagement'] / PD['engagement'].sum():.0%} を集めました。",
                          "その日の投稿の内容(テーマ・呼びかけ・見せ方)を確認し、似た企画を月に1〜2回行ってみましょう。"))
    types = breakdown_block(PD, "day_type", "投稿の種類")
    if types["ok"] and len([r for r in types["rows"] if r["rate"] is not None]) >= 2:
        v = [r for r in types["rows"] if r["rate"] is not None]
        b = max(v, key=lambda r: r["rate"])
        er_hyp.append(f"「{b['key']}」の日の{t('エンゲージメント率')}({b['rate']:.2%})が最も高くなっています。")
    if not er_hyp:
        er_hyp = [f"理由を考えるための数字が足りないため、{ND}です。"]
    comp = [(n, val(cur, k)) for k, n in [("likes", "いいね"), ("comments", "コメント"), ("saves", "保存"), ("shares", "シェア")]]
    comp_txt = "、".join(f"{n}が{v:,.0f}" for n, v in comp if v is not None)
    er_c = C["eng_rate"]
    pd_labels = [f"{mdw(r['dt'])} {r['day_type']}" for _, r in PD.iterrows()]
    deep_er = dict(
        key="engagement", title="反応のよさ(エンゲージメント率)", icon="❤️",
        terms=["エンゲージメント", "エンゲージメント率", "いいね", "コメント", "保存", "投稿した日", "pt(ポイント)"],
        reading=[f"この月の{t('エンゲージメント率')}は {fmt(val(cur, 'eng_rate'), 'rate')}"
                 + (f"(前回 {fmt(val(prev, 'eng_rate'), 'rate')}との差 {er_c['text']})" if er_c["cls"] != "nodata" else "(前回との比較は" + ND + ")")
                 + f"。反応の合計は {'・'.join(m.REACT_NAME[c] for c in react)} で計算しています。"],
        charts=[dict(title="投稿した日ごとのエンゲージメント率", svg=ch.bar_chart(pd_labels, [float(x) for x in PD["eng_rate"]], ch.fmt_pct, "投稿した日ごとのエンゲージメント率"),
                     comment=(f"→ いちばん高いのは {pd_labels[int(PD['eng_rate'].values.argmax())]} です。" if len(PD) else f"→ {ND}")),
                dict(title="この月の反応の内わけ", svg=ch.bar_chart([n for n, v in comp if v is not None], [v for n, v in comp if v is not None], ch.fmt_int, "反応の内わけ", highlight=False),
                     comment=(f"→ {comp_txt}でした。" + ("(シェアはこのデータにありません)" if "shares" not in react else "")) if comp_txt else f"→ 反応の数字は{ND}です。")]
        + ([dict(title="投稿の種類ごとのエンゲージメント率", svg=types["rate_svg"], comment=types["comment"])] if types["ok"] else []),
        hypotheses=er_hyp)

    # ======== 3) リーチ・インプレッション ========
    rh = []
    for col, nm in [("impressions", "インプレッション"), ("reach", "リーチ")]:
        sh = share_of_top(G, col)
        if sh and sh[1] >= 0.4:
            rh.append(f"{t(nm)}の {sh[1]:.0%} が、{mdw(sh[0])}の投稿に集中しています。")
    fq = val(cur, "frequency")
    if fq is not None:
        rh.append(f"{t('平均表示回数')}は {fq:.2f}回。" + ("1人が何度も見ていて、関心が高いのかもしれません。" if fq >= 2 else "多くの人は1〜2回見て終わっています。"))
    vv = G[G["video_views"] > 0]
    if len(vv):
        r_ = vv.iloc[-1]
        rh.append(f"{t('動画再生')}は {mdw(r_['dt'])}のリールで {r_['video_views']:,.0f}回、{t('リーチ')} {r_['reach']:,.0f}人 でした。")
    gap = _longest_gap(G)
    if gap and gap[0] >= 7:
        rh.append(f"{md(gap[1])}の次の投稿は{md(gap[2])}で、間に {gap[0]}日 投稿がありません。投稿がない間は、見られる回数のデータも{ND}です。")
        cands.append((90, "投稿の間をあけない(最低でも週1〜2回のペースを決める)",
                      f"フィードの投稿をした日は{int(cur['post_days'])}日だけで、{md(gap[1])}〜{md(gap[2])}の {gap[0]}日間は投稿がありません。",
                      "月の初めに投稿日を決めて(例: 毎週 火・金)、カレンダーに入れましょう。数字は投稿した日にしか増えないため、投稿の回数がそのまま「見られる回数」になります。"))
    if not rh:
        rh = [f"理由を考えるための数字が足りないため、{ND}です。"]
    deep_rc = dict(
        key="reach", title="どれだけ見られたか(リーチ・インプレッション)", icon="👀",
        terms=["リーチ", "インプレッション", "平均表示回数", "動画再生", "投稿した日"],
        reading=[f"投稿した日の合計で、{t('リーチ')}は {fmt(val(cur, 'reach'))}人、{t('インプレッション')}は {fmt(val(cur, 'impressions'))}回。"],
        charts=[dict(title="投稿した日ごとのリーチ(見た人の数)", svg=ch.bar_chart(pd_labels, [float(x) for x in PD["reach"]], ch.fmt_int, "投稿した日ごとのリーチ"),
                     comment=(f"→ 最も多く見られたのは {pd_labels[int(PD['reach'].values.argmax())]} です。" if len(PD) else f"→ {ND}")),
                dict(title="投稿した日ごとのインプレッション(見られた回数)", svg=ch.bar_chart(pd_labels, [float(x) for x in PD["impressions"]], ch.fmt_int, "投稿した日ごとのインプレッション"),
                     comment="→ 1人が何回も見るほど、リーチより大きな数字になります。")],
        hypotheses=rh,
        note="※リーチ・インプレッションは「その日に投稿した分」の数字です。投稿のない日は数字がありません(データなし)。リーチは日ごとの数字を足しているため、別の日に同じ人が見ていても重ねて数えています。")

    # ======== 4) プロフィール・リンク ========
    G2 = G.copy()
    pv = G2["profile_views"]
    ph = []
    if pv.notna().any():
        pk = G2.loc[pv.idxmax()]
        early, late = pv.iloc[:7].mean(), pv.iloc[7:].mean() if len(pv) > 7 else None
        ph.append(f"プロフィールがいちばん開かれたのは {mdw(pk['dt'])} の {pk['profile_views']:,.0f}回です。")
        if late is not None and early > late * 1.3:
            ph.append(f"1〜7日は1日平均 {early:,.0f}回、8日以降は {late:,.0f}回です。月のはじめに多く、その後は安定しています。")
        ppd, pnd = G2[G2["post_day"]]["profile_views"].mean(), G2[~G2["post_day"]]["profile_views"].mean()
        if pd.notna(ppd) and pd.notna(pnd):
            ph.append(f"投稿した日は1日平均 {ppd:,.0f}回、投稿しなかった日は {pnd:,.0f}回 プロフィールが開かれています。"
                      + ("投稿がない日にも見られているので、検索・紹介・広告などの別の入り口があるのかもしれません(仮説)。" if pnd >= ppd * 0.7 else ""))
    if lr is not None:
        ph.append(f"{t('リンククリック率')}は {lr:.2%}。プロフィールを開いた100回のうち約{lr * 100:.1f}回、リンクが押されています。")
        if lr < 0.05:
            cands.append((75, "プロフィールを見た人が、リンクを押したくなる形にする",
                          f"プロフィールは {fmt(val(cur, 'profile_visits'))}回 開かれましたが、リンクが押されたのは {fmt(val(cur, 'link_clicks'))}回({lr:.1%})です。",
                          "プロフィール文の最後に「▼予約・ご相談はこちら」と書き、リンク先を1つに絞りましょう。投稿の最後でも「プロフィールのリンクから」と案内します。"))
    others = {k: _s for k, _s in [("メール", G2["email_taps"]), ("電話", G2["phone_taps"]), ("道順", G2["direction_taps"])]}
    other_txt = "、".join(f"{k} {fmt(float(s.sum()) if s.notna().any() else None)}回" for k, s in others.items())
    if all(s.notna().any() and s.sum() == 0 for s in others.values()):
        ph.append("メール・電話・道順のタップは、すべて 0回 です。")
        cands.append((45, "メール・電話・道順のボタンを設定する(来店や問い合わせが目的なら)",
                      "メール・電話・道順のタップが今月は 0回 でした。",
                      "プロフィールの「連絡先オプション」で、電話・メール・道順のボタンを表示させましょう。ボタンが無いと、押したくても押せません。"))
    if not ph:
        ph = [f"理由を考えるための数字が足りないため、{ND}です。"]
    wd_rows = []
    for wd in [w + "曜日" for w in m.WEEKDAYS]:
        g = G2[G2["weekday"] == wd]
        wd_rows.append((f"{wd}({len(g)}日)", float(g["profile_views"].mean()) if len(g) and g["profile_views"].notna().any() else None))
    wdv = [(n, v) for n, v in wd_rows if v is not None]
    wd_best = max(wdv, key=lambda x: x[1]) if wdv else None
    link_wk = [None if not w["link_taps"].notna().any() else float(w["link_taps"].sum()) for _, w in wk]
    deep_pf = dict(
        key="profile", title="成果への入り口(プロフィール・リンク)", icon="🔗",
        terms=["プロフィールアクセス", "リンククリック", "リンククリック率", "前回比"],
        reading=[f"{t('プロフィールアクセス')}は {fmt(val(cur, 'profile_visits'))}回、{t('リンククリック')}は {fmt(val(cur, 'link_clicks'))}回。"
                 f"その他のボタン: {other_txt}。"],
        charts=[dict(title="プロフィールアクセスの推移(日ごと)", svg=ch.line_chart(dlabels, [("プロフィールアクセス", [None if pd.isna(v) else float(v) for v in pv])], ch.fmt_int, "プロフィールアクセスの推移"),
                     comment=trend_comment("プロフィールを開いた回数", C["profile_visits"], "「もっと知りたい」と思う人が増えています。", "プロフィールまで来る人が減っています。")
                     if C["profile_visits"]["cls"] != "nodata" else "→ 月のはじめが多く、その後は落ち着いた動きです。前回のデータがないため、先月との比較は" + ND + "です。"),
                dict(title="曜日ごとの平均プロフィールアクセス", svg=ch.bar_chart([n for n, _ in wd_rows], [v for _, v in wd_rows], ch.fmt_int, "曜日ごとの平均プロフィールアクセス"),
                     comment=(f"→ 平均がいちばん多いのは {wd_best[0].split('(')[0]} です(1日あたり {wd_best[1]:,.0f}回)。" if wd_best else f"→ {ND}")),
                dict(title="週ごとのリンククリック", svg=ch.bar_chart([w[0] for w in wk], link_wk, ch.fmt_int, "週ごとのリンククリック"),
                     comment="→ リンクが押された回数です。0に近い週は、リンクの案内を増やすチャンスです。"),
                dict(title="見られてから、リンクが押されるまで", svg=ch.bar_chart(["プロフィールを開いた回数", "リンクを押した回数"], [val(cur, "profile_visits"), val(cur, "link_clicks")], ch.fmt_int, "プロフィールからリンクまで", highlight=False),
                     comment="→ 上から下へ数字が小さくなるのがふつうです。落ち込みが大きいほど、リンクを見直す価値があります。")],
        hypotheses=ph)

    # ======== 5) フォロワーの属性 ========
    demo = dict(ok=False)
    if demo_raw is not None and not demo_raw.empty:
        dd = demo_raw[(pd.to_datetime(demo_raw["period_start"]) <= cur["end"]) & (pd.to_datetime(demo_raw["period_end"]) >= cur["start"])]
        if len(dd):
            last = dd["period_end"].max()
            dd = dd[dd["period_end"] == last]
            age, gen = dd[dd["kind"] == "age"], dd[dd["kind"] == "gender"]
            demo = dict(ok=True, period=f"{dd['period_start'].min()}〜{last}")
            hy, charts_, reading = [], [], []
            if len(age):
                age = age.assign(n=age["female_n"].fillna(0) + age["male_n"].fillna(0))
                tot = float(age["n"].sum())
                ag_labels = list(age["grp"])
                charts_.append(dict(title="年齢ごとのフォロワー数(分かった人だけ)", svg=ch.bar_chart(ag_labels, [float(x) for x in age["n"]], ch.fmt_int, "年齢ごとのフォロワー数"),
                                    comment=f"→ いちばん多いのは {age.loc[age['n'].idxmax(), 'grp']} です({age['n'].max() / tot:.0%})。" if tot else f"→ {ND}"))
                if tot:
                    srt = age.sort_values("n", ascending=False)
                    top2 = srt.head(2)
                    hy.append(f"多い順に {top2.iloc[0]['grp']}({top2.iloc[0]['n'] / tot:.1%})、{top2.iloc[1]['grp']}({top2.iloc[1]['n'] / tot:.1%})で、2つ合わせて {top2['n'].sum() / tot:.1%} です。"
                              if len(top2) == 2 else f"{top2.iloc[0]['grp']}が最も多くなっています。")
                    reading.append(f"年齢が分かったフォロワーは合計 {tot:,.0f}人です(フォロワー数 {fmt(fol_end)}人のうち、属性が分かった人の分だけ)。")
                    if len(top2) == 2:
                        cands.append((55, f"いちばん多い層({top2.iloc[0]['grp']}・{top2.iloc[1]['grp']})に向けた内容にする",
                                      f"{t('フォロワーの属性')}では、{top2.iloc[0]['grp']}と{top2.iloc[1]['grp']}で全体の {top2['n'].sum() / tot:.0%} を占めています。",
                                      "この年代の悩みや関心(例: 年齢にあわせたお手入れ・選び方)を投稿のテーマにしましょう。言葉づかいや、見られやすい時間帯もこの層に合わせます。"))
            if len(gen):
                g = gen.iloc[0]
                fn, mn = g["female_n"], g["male_n"]
                gt = (fn or 0) + (mn or 0)
                charts_.append(dict(title="性別ごとのフォロワー数(分かった人だけ)", svg=ch.bar_chart(["女性", "男性"], [fn, mn], ch.fmt_int, "性別ごとのフォロワー数"),
                                    comment=f"→ 女性が {fn / gt:.1%}、男性が {mn / gt:.1%} です。" if gt else f"→ {ND}"))
                if gt:
                    hy.append(f"女性が {fn / gt:.1%}({fn:,.0f}人)、男性が {mn / gt:.1%}({mn:,.0f}人)です。ほぼ女性向けのアカウントになっています。" if fn / gt >= 0.8 else
                              f"女性 {fn / gt:.1%}、男性 {mn / gt:.1%} で、男女どちらにも見られています。")
            demo.update(charts=charts_, hypotheses=hy or [f"{ND}"], reading=reading)
    deep_demo = dict(key="demo", title="フォロワーはどんな人?(年齢・性別)", icon="🧑‍🤝‍🧑", terms=["フォロワーの属性", "フォロワー数"],
                     reading=demo.get("reading") or [f"この期間のフォロワーの年齢・性別は{ND}です。「➕ 新しいデータを追加」でファイルを入れてください。"],
                     charts=demo.get("charts", []), hypotheses=demo.get("hypotheses", [f"{ND}"]),
                     note="※年齢・性別は、Instagramが「分かった」フォロワーだけの数字です。ファイルの%の列は計算の元になる人数が揃っていないため、人数から計算し直しています。" if demo["ok"] else "")

    # --- 投稿した日の分析 ---
    posts_sec = posts_section(PD)
    wd = breakdown_block(PD, "weekday", "曜日別", [w + "曜日" for w in m.WEEKDAYS])
    hr = breakdown_block(PD, "bucket", "時間帯別")
    for blk, nm in [(types, "投稿の種類"), (wd, "曜日")]:
        v = [r for r in blk.get("rows", []) if r["rate"] is not None and r["n"] >= 2]
        if len(v) >= 2:
            b, w = max(v, key=lambda r: r["rate"]), min(v, key=lambda r: r["rate"])
            if b["rate"] / w["rate"] - 1 >= 0.15:
                cands.append((70, f"{nm}は「{b['key']}」を増やす",
                              f"{nm}ごとに比べると、「{b['key']}」の{t('エンゲージメント率')}が{b['rate']:.2%}で、「{w['key']}」の{w['rate']:.2%}より{b['rate'] / w['rate'] - 1:.0%}高くなっています(日数 {b['n']}日と{w['n']}日)。",
                              f"次の1か月は「{b['key']}」の投稿を今より増やし、「{w['key']}」は内容を見直しながら様子を見ましょう。"))
    if len(cands) < 3:
        cands.append((10, "毎月、同じ形式のデータを追加して、比べられる土台をつくる",
                      "比較できる過去の月が少ないと、増減の理由を探しにくくなります。",
                      "毎月、同じ5種類のファイルを追加してください。2か月分たまると「前回比」、4か月分で「3か月前との比較」が使えます。"))
    cands.sort(key=lambda c: -c[0])
    suggestions = [dict(title=a[1], why=a[2], how=a[3]) for a in cands[:5]]

    # --- データについての注意(読み方) ---
    if days < cur["days_in_month"]:
        notes.append(f"この月のデータは {days}日分です(月は{int(cur['days_in_month'])}日)。ほかの月と比べるときは、日数の違いに注意してください。")
    notes.append("フォロワー数: ファイルの「フォロワー数」は、その日のはじめの人数です(翌日の数字との差が、その日の増減と一致するため)。"
                 "そのため月末の人数は「最終日の数字 + 最終日の増減」で計算しています。実際の人数はInstagramアプリで確認してください。")
    ns, gs = m._sum(G["new_followers"]), m._sum(G["follower_net"])
    if ns is not None and gs is not None and abs(ns - gs) >= 1:
        notes.append(f"「新規フォロワー数」の合計({ns:,.0f}人)と「フォロワー増減」の合計({gs:,.0f}人)が一致しません。このレポートは「フォロワー増減」を使っています。")
    notes.append("リーチ・インプレッション・いいね・コメント・保存は「その日に投稿した分の合計」です。投稿1本ずつの数字と、投稿した時刻は、このデータには含まれていません(データなし)。")
    notes.append("反応の合計(エンゲージメント)は「" + "・".join(m.REACT_NAME[c] for c in react) + "」で計算しています。"
                 + ("" if "shares" in react else "シェアのデータが無いため、含まれていません。"))
    notes.append("ストーリーズは、投稿した本数だけで、見られた回数などの数字はデータなしです。")
    if prev is None:
        notes.append("前回(先月)など、比べる相手の月のデータがまだ無いため、「前回比」は データなし と表示しています。来月分を追加すると、矢印つきで自動で比べます。")

    # --- 会議メモ ---
    memo = dict(prev_next="", prev_date="", cur_decided="", cur_date="")
    if meetings is not None and not meetings.empty:
        done = meetings[pd.to_datetime(meetings["meeting_date"]) <= cur["end"] + pd.Timedelta(days=45)]
        if len(done):
            last = done.iloc[-1]
            memo.update(cur_date=last["meeting_date"], cur_decided=last["decided"], prev_next=last["next_actions"])

    return dict(
        client=client_name, account=account or (G["account"].iloc[0] if len(G) else ""), sns="Instagram",
        period=period_text(cur) + f"({days}日分)", period_label=month_label(cur), period_key=cur["id"], created=datetime.now().strftime("%Y/%m/%d %H:%M"),
        n_periods=len(S), summary=summary, changes=changes, ref_names=[r[0] for r in refs],
        ref_periods=[f"{r['start'].year}年{r['start'].month}月" if r is not None else ND for _, r in refs],
        posts=posts_sec, breakdowns=[types, wd, hr], follower_chart=follower_chart,
        deep=[deep_fol, deep_er, deep_rc, deep_pf, deep_demo], suggestions=suggestions, memo=memo, data_notes=notes,
        glossary=[dict(term=a, meaning=b, guide=c) for a, b, c in GLOSSARY],
        glossary_map={a: b for a, b, c in GLOSSARY},
        series=dict(labels=dlabels, followers=[None if pd.isna(v) else float(v) for v in G["end_followers"]],
                    gain=[None if pd.isna(v) else float(v) for v in G["follower_net"]]),
        daily_df=G, monthly_df=S,
    )
