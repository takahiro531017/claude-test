"""分析の中身づくり。画面・HTML・PDF・Excelはすべてここで作った dict を使う。
文章は数字から機械的に作り、断定せず「〜かもしれません」と書く。データが足りない項目は「データなし」。"""
from datetime import datetime

import pandas as pd

from . import charts as ch
from . import db as db_types
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
SHORT = {"followers": "フォローしている人の数", "follower_gain": "期間中に増えた人数(新規−解除)",
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
    if kind == "delta":
        flat = diff == 0
    else:
        flat = (abs(pct) < FLAT) if pct is not None else diff == 0
    arrow = "→" if flat else ("↑" if diff > 0 else "↓")
    cls = "flat" if flat else ("up" if diff > 0 else "down")
    if kind == "rate":
        text = f"{arrow} {diff * 100:+.2f}pt"
    elif kind == "delta":
        text = f"{arrow} {diff:+,.0f}人"
    else:
        text = f"{arrow} {diff:+,.0f}" + (f"({pct:+.1%})" if pct is not None else "")
    return dict(text=text, arrow=arrow, cls=cls, pct=pct, diff=diff)


def pct_txt(p):
    return ND if p is None else f"{p:+.1%}"


def trend_comment(label, c, up_msg, down_msg, flat_msg=None, ref_name="前回"):
    if c["cls"] == "nodata":
        return f"→ {ref_name}のデータがないため、{label}の変化は{ND}です。"
    if c["cls"] == "flat":
        return f"→ {label}は{ref_name}とほぼ同じです。" + (flat_msg or "")
    if c["cls"] == "up":
        return f"→ {ref_name}より{label}が増えています。{up_msg}"
    return f"→ {ref_name}より{label}が減っています。{down_msg}"


def label_of(row):
    s, e = row["start"], row["end"]
    if s.day == 1 and (e + pd.Timedelta(days=1)).day == 1 and s.month == e.month:
        return f"{e.month}月"
    return f"{e.month}/{e.day}"


def period_text(row):
    return f"{row['start']:%Y/%m/%d}〜{row['end']:%Y/%m/%d}"


# ---------- 投稿ごとの分析 ----------
def post_view(r):
    return dict(date=str(r["posted_at"]), type=r["post_type"], theme=r.get("theme") or "", reach=fmt(val(r, "reach")),
                rate=fmt(val(r, "eng_rate"), "rate"), saves=fmt(val(r, "saves")), likes=fmt(val(r, "likes")))


def post_factors(p, P):
    """この投稿の数字が、全体平均よりどれだけ違うかを理由の候補として並べる(差が大きい順)。"""
    overall = m.pooled_rate(P, "engagement", "reach")
    out = []
    if overall:
        for col, label in [("post_type", "投稿の種類"), ("theme", "テーマ"), ("weekday", "曜日"), ("bucket", "投稿した時間帯")]:
            k = p.get(col)
            if k in (None, "") or pd.isna(k):
                continue
            g = P[P[col] == k]
            rate = m.pooled_rate(g, "engagement", "reach")
            if len(g) >= 2 and rate is not None:
                dev = rate / overall - 1
                out.append((dev, f"同じ{label}「{k}」の投稿({len(g)}本)は、全体より{t('エンゲージメント率')}が{abs(dev):.0%}"
                                 f"{'高い' if dev > 0 else '低い'}傾向があります"))
    sr, osr = val(p, "save_rate"), m.pooled_rate(P, "saves", "reach")
    if sr is not None and osr:
        dev = sr / osr - 1
        out.append((dev, f"この投稿の{t('保存率')}は{sr:.2%}で、全体の{osr:.2%}より{abs(dev):.0%}{'高く' if dev > 0 else '低く'}なっています"))
    rv, avg = val(p, "reach"), P["reach"].mean()
    if rv is not None and avg and not pd.isna(avg):
        dev = rv / avg - 1
        out.append((dev, f"この投稿の{t('リーチ')}は{rv:,.0f}で、全体の平均{avg:,.0f}より{abs(dev):.0%}{'多く' if dev > 0 else '少なく'}なっています"))
    return out


def hypothesis(p, P, good):
    f = [x for x in post_factors(p, P) if abs(x[0]) >= 0.1 and (x[0] > 0) == good]
    f.sort(key=lambda x: -abs(x[0]))
    if not f:
        return "はっきりした理由は、今ある数字からは見つかりませんでした(データ不足)。"
    return "。".join(s for _, s in f[:2]) + "。そのため、これが理由かもしれません(仮説です)。"


def posts_section(P):
    if P.empty:
        return dict(ok=False, note=f"この期間の投稿ごとのデータは{ND}です。「新しいデータを追加」から投稿ごとの数字を入れてください。")
    R = P.dropna(subset=["eng_rate"]).sort_values("eng_rate", ascending=False)
    if len(R) < 2:
        return dict(ok=False, note=f"{t('エンゲージメント率')}を計算できる投稿が足りないため、{ND}です。")
    top = R.head(3)
    worst = R.drop(top.index).tail(3).iloc[::-1] if len(R) > 3 else R.iloc[0:0]
    return dict(ok=True, note="",
                top=[dict(**post_view(r), why=hypothesis(r, P, True)) for _, r in top.iterrows()],
                worst=[dict(**post_view(r), why=hypothesis(r, P, False)) for _, r in worst.iterrows()],
                n=len(P))


def breakdown_block(P, col, title, order=None):
    rows = m.breakdown(P, col, order)
    if len(rows) < 1:
        return dict(title=title, ok=False, note=f"{title}の比較に使えるデータは{ND}です"
                    + ("(投稿の時刻が入っていません)" if col == "bucket" else "") + "。")
    labels = [f"{r['key']}({r['n']}本)" for r in rows]
    rate = ch.bar_chart(labels, [r["rate"] for r in rows], ch.fmt_pct, f"{title}の{'エンゲージメント率'}")
    reach = ch.bar_chart(labels, [r["avg_reach"] for r in rows], ch.fmt_int, f"{title}の平均リーチ")
    valid = [r for r in rows if r["rate"] is not None]
    if len(valid) >= 2:
        b, w = max(valid, key=lambda r: r["rate"]), min(valid, key=lambda r: r["rate"])
        cm = (f"→ 「{b['key']}」の{t('エンゲージメント率')}が{b['rate']:.2%}でいちばん高く、「{w['key']}」が{w['rate']:.2%}で最も低いです。"
              + ("ただし投稿数が少ない(5本未満)グループがあるため、参考程度に見てください。" if min(r["n"] for r in valid) < 5 else ""))
    else:
        cm = f"→ 比べられるグループが1つだけのため、良し悪しの比較は{ND}です。"
    return dict(title=title, ok=True, rate_svg=rate, reach_svg=reach, comment=cm, rows=rows)


# ---------- 深掘り(1指標1ページ) ----------
def build_analysis(client_name, snaps_raw, posts_raw, meetings, cur_id=None, account=""):
    S = m.prepare_snapshots(snaps_raw)
    if S.empty:
        return None
    idx = len(S) - 1 if cur_id is None else int(S.index[S["id"] == cur_id][0])
    cur = S.iloc[idx]
    cands = []  # (優先度, タイトル, 理由, やり方)

    refs = [("前回", m.find_ref(S, idx)), ("1か月前", m.find_ref(S, idx, 30, 10)), ("3か月前", m.find_ref(S, idx, 90, 20))]
    P = m.period_posts(m.prepare_posts(posts_raw) if not posts_raw.empty else posts_raw, cur["start"], cur["end"])
    prev = refs[0][1]
    N = idx + 1
    series_rows = S.iloc[max(0, idx - 11): idx + 1]
    labels = [label_of(r) for _, r in series_rows.iterrows()]

    def seq(key):
        return [None if pd.isna(v) else float(v) for v in series_rows[key]]

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
    C = {r["key"]: r["cells"][0] for r in changes}       # 前回比

    # --- まとめ3行 ---
    def line(key, name, kind, tail):
        c = C[key]
        base = f"{t(name) if name in ('リーチ', 'エンゲージメント率') else name}は {fmt(val(cur, key), kind)}"
        if c["cls"] == "nodata":
            return f"{base}。前回との比較は{ND}です。"
        return f"{base}。前回より {c['text']}。{tail[c['cls']]}"
    summary = [
        line("followers", "フォロワー数", "count",
             dict(up="フォロワーが増えました。", down="フォロワーが減りました。理由を探しましょう。", flat="大きな変化はありません。")),
        line("reach", "リーチ", "count",
             dict(up="見た人が増えています。", down="見た人が減っています。", flat="ほぼ同じ人数に届いています。")),
        line("eng_rate", "エンゲージメント率", "rate",
             dict(up="反応する人の割合が上がりました。", down="反応する人の割合が下がりました。", flat="反応の割合は変わっていません。")),
    ]

    # 1) フォロワー
    gain, gain_c = val(cur, "follower_gain"), C["follower_gain"]
    fol_hyp = []
    if C["reach"]["cls"] != "nodata" and gain_c["cls"] != "nodata":
        if gain_c["cls"] == "up" and C["reach"]["cls"] == "up":
            fol_hyp.append(f"{t('リーチ')}も増えているため、見た人が増えたことで新しいフォロワーが増えたのかもしれません。")
        elif gain_c["cls"] == "down" and C["reach"]["cls"] == "down":
            fol_hyp.append(f"{t('リーチ')}も減っているため、見られる人が減ったことが増加の鈍りに関係しているのかもしれません。")
        elif gain_c["cls"] == "down":
            fol_hyp.append(f"{t('リーチ')}は減っていないのに増加数が下がっています。見た人がフォローまでしなかった可能性があります。")
    if C["profile_visits"]["cls"] != "nodata" and gain_c["cls"] in ("up", "down"):
        fol_hyp.append(f"{t('プロフィールアクセス')}は前回比 {C['profile_visits']['text']} です。プロフィールを見る人の動きとフォローの増減が連動している可能性があります。")
    if not fol_hyp:
        fol_hyp = [f"理由を考えるための数字が足りないため、{ND}です。"]
    if gain is not None and gain <= 0:
        cands.append((90, "フォローしたくなるプロフィールに整える",
                      f"今回の{t('フォロワー増加数')}が{gain:+,.0f}人でした。",
                      "プロフィール文に「何を発信しているか」「フォローすると得すること」を1行で書き、固定投稿を代表的な3本にそろえましょう。"))
    gain_bars = ch.bar_chart(labels, seq("follower_gain"), lambda v: ND if v is None else f"{v:+,.0f}人", "期間ごとのフォロワー増加数")
    deep_fol = dict(
        key="followers", title="フォロワーの増え方", icon="👥",
        terms=["フォロワー数", "フォロワー増加数", "前回比"],
        reading=[f"今のフォロワー数は {fmt(val(cur, 'followers'))}人。前回から {fmt(gain, 'delta')}人({pct_txt(change(val(cur, 'followers'), val(prev, 'followers'))['pct'])})。"],
        charts=[dict(title="フォロワー数の推移", svg=ch.line_chart(labels, [("フォロワー数", seq("followers"))], ch.fmt_int, "フォロワー数の推移"),
                     comment=trend_comment("フォロワー数", C["followers"], "応援してくれる人が増えています。", "フォローを外す人が増えたか、増える勢いが弱まった可能性があります。")),
                dict(title="期間ごとの増えた人数", svg=gain_bars,
                     comment=trend_comment("増えた人数", gain_c, "増えるペースが上がっています。", "増えるペースが落ちています。原因を探しましょう。"))],
        hypotheses=fol_hyp)
    follower_chart = deep_fol["charts"][0]

    # 2) エンゲージメント率
    er_hyp = []
    if C["saves"]["cls"] != "nodata":
        er_hyp.append(f"{t('保存')}は前回比 {C['saves']['text']}。" +
                      ("役に立つ投稿が好まれているのかもしれません。" if C["saves"]["cls"] == "up" else
                       "保存したくなる(役立つ)投稿が減っているのかもしれません。" if C["saves"]["cls"] == "down" else "保存の数は安定しています。"))
    if C["shares"]["cls"] in ("up", "down"):
        er_hyp.append(f"{t('シェア')}は前回比 {C['shares']['text']}。人にすすめたくなる投稿の量が変わった可能性があります。")
    er_pt = breakdown_block(P, "post_type", "投稿の種類", db_types.POST_TYPES)
    types_ok = er_pt["ok"] and len([r for r in er_pt["rows"] if r["rate"] is not None]) >= 2
    if types_ok:
        v = [r for r in er_pt["rows"] if r["rate"] is not None]
        b = max(v, key=lambda r: r["rate"])
        er_hyp.append(f"今回の投稿では「{b['key']}」の{t('エンゲージメント率')}({b['rate']:.2%})が最も高く、この形が合っているのかもしれません。")
    if not er_hyp:
        er_hyp = [f"理由を考えるための数字が足りないため、{ND}です。"]
    comp_labels = ["いいね", "コメント", "保存", "シェア"]
    comp_vals = [val(cur, k) for k in ("likes", "comments", "saves", "shares")]
    er_c = C["eng_rate"]
    if er_c["cls"] == "down":
        cands.append((85, "反応(保存・シェア)されやすい投稿を増やす",
                      f"{t('エンゲージメント率')}が前回より {er_c['text']} 下がりました。",
                      "「あとで見返したくなる」まとめ・ノウハウ系の投稿を、次の1か月で2〜3本増やしてみましょう。投稿の最後に「保存してね」の一言を添えるのも手です。"))
    elif er_c["cls"] == "up":
        cands.append((50, "反応が良かった投稿の型を続ける",
                      f"{t('エンゲージメント率')}が前回より {er_c['text']} 上がりました。",
                      "今回のベスト3の投稿の「テーマ・形・見せ方」を、次の投稿にも取り入れましょう。"))
    deep_er = dict(
        key="engagement", title="反応のよさ(エンゲージメント率)", icon="❤️",
        terms=["エンゲージメント", "エンゲージメント率", "いいね", "コメント", "保存", "シェア", "pt(ポイント)"],
        reading=[f"今回の{t('エンゲージメント率')}は {fmt(val(cur, 'eng_rate'), 'rate')}。前回({fmt(val(prev, 'eng_rate'), 'rate')})との差は {er_c['text']}。"],
        charts=[dict(title="エンゲージメント率の推移", svg=ch.line_chart(labels, [("エンゲージメント率", seq("eng_rate"))], ch.fmt_pct, "エンゲージメント率の推移"),
                     comment=trend_comment("反応する人の割合", er_c, "見た人が反応してくれやすくなっています。", "見ても反応しない人が増えています。投稿の内容を見直すチャンスです。")),
                dict(title="今回の反応の内わけ", svg=ch.bar_chart(comp_labels, comp_vals, ch.fmt_int, "反応の内わけ", highlight=False),
                     comment=("→ " + ("、".join(f"{l}が{v:,.0f}" for l, v in zip(comp_labels, comp_vals) if v is not None) + "でした。"
                              + (f"{t('保存')}は{t('いいね')}の{comp_vals[2] / comp_vals[0]:.0%}にあたります。" if comp_vals[0] and comp_vals[2] is not None else ""))
                              if any(v is not None for v in comp_vals) else f"→ 反応の数字は{ND}です。"))]
                + ([dict(title="投稿の種類ごとのエンゲージメント率", svg=er_pt["rate_svg"], comment=er_pt["comment"])] if er_pt["ok"] else []),
        hypotheses=er_hyp)

    # 3) リーチ・インプレッション
    rc, ic = C["reach"], C["impressions"]
    rh = []
    if rc["cls"] != "nodata":
        rh.append(f"{t('リーチ')}は前回比 {rc['text']}、{t('インプレッション')}は前回比 {ic['text']} です。"
                  + ("見てくれる人の数が増えたことが、見られた回数の増加につながっているのかもしれません。" if rc["cls"] == "up" and ic["cls"] == "up" else
                     "見てくれる人が減ったことが、見られた回数の減少につながっているのかもしれません。" if rc["cls"] == "down" and ic["cls"] == "down" else ""))
    fq, fq_prev = val(cur, "frequency"), val(prev, "frequency")
    if fq is not None:
        rh.append(f"{t('平均表示回数')}は {fq:.2f}回" + (f"(前回 {fq_prev:.2f}回)" if fq_prev is not None else "") + "。"
                  + ("1人が何度も見ていて、関心が高いのかもしれません。" if fq >= 2 else "多くの人は1〜2回見て終わっています。"))
    fl, rv = val(cur, "followers"), val(cur, "reach")
    if fl and rv is not None:
        rh.append(f"{t('リーチ')}はフォロワー数の {rv / fl:.0%} にあたります。" +
                  ("100%を超えているため、フォロワー以外の人にも届いています。" if rv > fl else "まだフォロワー全員には届いていません。"))
    if not rh:
        rh = [f"理由を考えるための数字が足りないため、{ND}です。"]
    if rc["cls"] == "down":
        cands.append((88, "新しい人に届きやすい投稿を試す",
                      f"{t('リーチ')}が前回より {rc['text']} 減りました。",
                      "リール(短い縦型動画)など、フォロワー以外にも届きやすいといわれる形式を、今より1〜2本多く試してみましょう。"))
    deep_rc = dict(
        key="reach", title="どれだけ見られたか(リーチ・インプレッション)", icon="👀",
        terms=["リーチ", "インプレッション", "平均表示回数"],
        reading=[f"{t('リーチ')}は {fmt(val(cur, 'reach'))}人、{t('インプレッション')}は {fmt(val(cur, 'impressions'))}回。"],
        charts=[dict(title="リーチとインプレッションの推移", svg=ch.line_chart(labels, [("インプレッション(回数)", seq("impressions")), ("リーチ(人数)", seq("reach"))], ch.fmt_int, "リーチとインプレッションの推移"),
                     comment=trend_comment("見られた回数と人数", ic, "多くの人の目にとまっています。", "見られる機会が減っています。投稿の頻度や形式を見直しましょう。")),
                dict(title="1人あたりの平均表示回数", svg=ch.line_chart(labels, [("平均表示回数", seq("frequency"))], ch.fmt_dec, "平均表示回数の推移"),
                     comment="→ 数字が高いほど、同じ人に何度も見られています(1.0なら1人1回)。")],
        hypotheses=rh)

    # 4) プロフィール・リンク
    pr, lr = val(cur, "profile_rate"), val(cur, "link_rate")
    ph = []
    if pr is not None:
        ph.append(f"{t('プロフィールアクセス率')}は {pr:.2%}。見た人100人のうち約{pr * 100:.1f}人がプロフィールを開いています。")
    if lr is not None:
        ph.append(f"{t('リンククリック率')}は {lr:.2%}。プロフィールを開いた100人のうち約{lr * 100:.0f}人がリンクを押しています。")
    if pr is not None and C["profile_visits"]["cls"] == "up" and C["link_clicks"]["cls"] == "down":
        ph.append("プロフィールを開く人は増えたのにリンクは押されていません。リンクの場所や書き方が分かりにくいのかもしれません。")
        cands.append((86, "プロフィールのリンクを見つけやすくする",
                      f"{t('プロフィールアクセス')}は増えたのに、{t('リンククリック')}は前回比 {C['link_clicks']['text']} でした。",
                      "プロフィール文の最後に「▼予約・ご注文はこちら」と書き、リンク先を1つに絞りましょう。投稿の最後でもリンクに誘導します。"))
    elif C["link_clicks"]["cls"] == "down":
        cands.append((80, "リンクを押してもらう呼びかけを増やす",
                      f"{t('リンククリック')}が前回比 {C['link_clicks']['text']} でした。",
                      "投稿の最後に「くわしくはプロフィールのリンクから」と一言そえ、ストーリーズでもリンクの場所を案内しましょう。"))
    if not ph:
        ph = [f"理由を考えるための数字が足りないため、{ND}です。"]
    funnel = [val(cur, "reach"), val(cur, "profile_visits"), val(cur, "link_clicks")]
    deep_pf = dict(
        key="profile", title="成果への入り口(プロフィール・リンク)", icon="🔗",
        terms=["プロフィールアクセス", "プロフィールアクセス率", "リンククリック", "リンククリック率"],
        reading=[f"{t('プロフィールアクセス')}は {fmt(val(cur, 'profile_visits'))}回、{t('リンククリック')}は {fmt(val(cur, 'link_clicks'))}回。"],
        charts=[dict(title="見られてから、リンクが押されるまで", svg=ch.bar_chart(["見た人(リーチ)", "プロフィールを開いた回数", "リンクを押した回数"], funnel, ch.fmt_int, "見られてからリンクが押されるまで", highlight=False),
                     comment="→ 上から下へ数字が小さくなるのがふつうです。落ち込みが大きい段が、改善の狙い目です。"),
                dict(title="プロフィールアクセス・リンククリックの推移", svg=ch.line_chart(labels, [("プロフィールアクセス", seq("profile_visits")), ("リンククリック", seq("link_clicks"))], ch.fmt_int, "プロフィールアクセスとリンククリックの推移"),
                     comment=trend_comment("プロフィールを開いた回数", C["profile_visits"], "「もっと知りたい」と思う人が増えています。", "プロフィールまで来る人が減っています。投稿の最後で誘導してみましょう。"))],
        hypotheses=ph)

    # --- 投稿ベスト/ワースト・比較 ---
    posts_sec = posts_section(P)
    types = er_pt
    wd = breakdown_block(P, "weekday", "曜日別", [w + "曜日" for w in m.WEEKDAYS])
    hr = breakdown_block(P, "bucket", "時間帯別", [b[0] for b in m.BUCKETS])
    for blk, nm in [(types, "投稿の種類"), (wd, "曜日"), (hr, "時間帯")]:
        v = [r for r in blk.get("rows", []) if r["rate"] is not None and r["n"] >= 2]
        if len(v) >= 2:
            b, w = max(v, key=lambda r: r["rate"]), min(v, key=lambda r: r["rate"])
            if b["rate"] / w["rate"] - 1 >= 0.15:
                cands.append((70 if nm != "投稿の種類" else 75, f"{nm}は「{b['key']}」を増やす",
                              f"{nm}ごとに比べると、「{b['key']}」の{t('エンゲージメント率')}が{b['rate']:.2%}で、「{w['key']}」の{w['rate']:.2%}より{b['rate'] / w['rate'] - 1:.0%}高くなっています(投稿数 {b['n']}本と{w['n']}本)。",
                              f"次の1か月は「{b['key']}」の投稿を今より1〜2本多くし、「{w['key']}」は内容を見直しながら様子を見ましょう。"))
    if not any("時間帯" in c[1] or "曜日" in c[1] for c in cands) and (hr["ok"] is False or wd["ok"] is False):
        cands.append((20, "投稿の時刻を記録して、曜日・時間帯の比較をできるようにする",
                      f"曜日別・時間帯別の比較に使える数字が足りません({ND})。",
                      "投稿ごとのデータを入れるときに、投稿した日時(時刻まで)を入れてください。"))
    if len(cands) < 3:
        cands.append((10, "毎回同じ指標を同じ期間の長さで記録して、比べられる土台をつくる",
                      "比較できる過去データが少ないと、増減の理由を探しにくくなります。",
                      "毎月(または毎週)、同じ長さの期間で数字を追加してください。3回分たまると「3か月前との比較」も使えます。"))
    if len(cands) < 3:
        cands.append((9, "会議で決めたことを、次回の数字で振り返る",
                      "やったことと数字の変化をセットで見ると、何が効いたかが分かります。",
                      "「会議メモ」に決めたことを残し、次回のレポートで「前回比」の矢印と見比べましょう。"))
    cands.sort(key=lambda c: -c[0])
    suggestions = [dict(title=a[1], why=a[2], how=a[3]) for a in cands[:5]]

    # --- 会議メモ ---
    memo = dict(prev_next="", prev_date="", cur_decided="", cur_date="")
    if meetings is not None and not meetings.empty:
        done = meetings[pd.to_datetime(meetings["meeting_date"]) <= cur["end"] + pd.Timedelta(days=45)]
        if len(done):
            last = done.iloc[-1]
            memo.update(cur_date=last["meeting_date"], cur_decided=last["decided"], prev_next=last["next_actions"])

    return dict(
        client=client_name, account=account or cur.get("account", ""), sns="Instagram",
        period=period_text(cur), period_label=label_of(cur), created=datetime.now().strftime("%Y/%m/%d %H:%M"),
        n_periods=N, summary=summary, changes=changes, ref_names=[r[0] for r in refs],
        ref_periods=[period_text(r) if r is not None else ND for _, r in refs],
        posts=posts_sec, breakdowns=[types, wd, hr], follower_chart=follower_chart,
        deep=[deep_fol, deep_er, deep_rc, deep_pf], suggestions=suggestions, memo=memo,
        glossary=[dict(term=a, meaning=b, guide=c) for a, b, c in GLOSSARY],
        glossary_map={a: b for a, b, c in GLOSSARY},
        series=dict(labels=labels, followers=seq("followers"), gain=seq("follower_gain"), reach=seq("reach"),
                    impressions=seq("impressions"), eng_rate=seq("eng_rate")),
        posts_df=P, snaps_df=S,
    )
