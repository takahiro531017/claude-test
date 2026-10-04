"""SNS運用代行 分析アプリ(Instagram)。起動: streamlit run app.py"""
import os
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from snsapp import analysis, db, importer, report
from snsapp import charts as ch
from snsapp.db import DAILY_FIELDS, diff_edits
from snsapp.glossary import GLOSSARY

st.set_page_config(page_title="SNS分析アプリ", page_icon="📊", layout="wide")
db.init_db()
SAMPLE_DIR = Path(__file__).parent / "sample"
COUNT_FIELDS = [f for f in DAILY_FIELDS if f[0].startswith("posts_")]
NUM_FIELDS = [f for f in DAILY_FIELDS if not f[0].startswith("posts_")]


def show(html: str):
    st.html(html)


def parse_num(text, label, required=False, allow_negative=False):
    """入力欄の文字を数字にする。(値, エラー文)。空欄は「データなし」として保存。"""
    s = (text or "").strip().replace(",", "").replace("、", "")
    if not s:
        return None, (f"「{label}」は必須です。" if required else None)
    try:
        v = float(s)
    except ValueError:
        return None, f"「{label}」は数字で入力してください(例: 1250)。"
    if v < 0 and not allow_negative:
        return None, f"「{label}」にマイナスの数字は入れられません。"
    return v, None


def load_files(client_id, items, overwrite=False):
    """[(ファイル名, bytes)] をまとめて取り込む。結果の文章のリストを返す。"""
    out = []
    for name, raw in items:
        p = importer.plan_file(name, raw)
        if p["error"]:
            out.append(f"{name}: {p['error']}")
            continue
        acc = p["account"] or ""
        out.append(f"{name}({importer.KIND_LABEL[p['kind']]}): " + importer.import_plan(db, client_id, p, acc, p["kind"], p["start"], p["end"], overwrite))
    return out


# ------------------------------------------------------------ クライアント選択
clients = db.clients_df()
if clients.empty:
    st.title("📊 SNS分析アプリ")
    st.info("まだデータがありません。最初にクライアント名を決めて、データを入れましょう。")
    nm = st.text_input("クライアント名(会社名)", placeholder="例: 株式会社サンプル")
    c1, c2 = st.columns(2)
    if c1.button("クライアントをつくる", type="primary") and nm.strip():
        db.add_client(nm)
        st.rerun()
    samples = sorted(SAMPLE_DIR.glob("*.xlsx"))
    if samples:
        st.write("または、`sample/` フォルダのインサイトのファイル(Instagram 2026年9月分)を読み込んで、すぐに試せます。")
        if c2.button("サンプルのファイルを読み込む"):
            cid = db.get_or_add_client("venusisbeauty")
            for line in load_files(cid, [(f.name, f.read_bytes()) for f in samples]):
                st.write("・" + line)
            st.rerun()
    st.stop()

PAGES = ["🏠 ホーム(まとめ)", "➕ 新しいデータを追加", "🛠 データの確認・修正・削除", "🔎 深掘り:フォロワー", "🔎 深掘り:反応(エンゲージメント率)",
         "🔎 深掘り:リーチ・インプレッション", "🔎 深掘り:プロフィール・リンク", "🔎 深掘り:フォロワーの属性", "🖼 投稿した日の分析",
         "⏪ 過去との比較", "📄 分析ファイルを作る", "📖 用語集", "❓ 使い方"]
with st.sidebar:
    st.title("📊 SNS分析アプリ")
    client_name = st.selectbox("クライアント", clients["name"].tolist())
    client_id = int(clients.loc[clients["name"] == client_name, "id"].iloc[0])
    with st.expander("＋ クライアントを追加"):
        nn = st.text_input("会社名(新規)", key="new_client")
        if st.button("追加する") and nn.strip():
            try:
                db.add_client(nn)
                st.rerun()
            except Exception:
                st.error("同じ名前のクライアントが既にあります。")
    daily_all = db.daily_df(client_id)
    accounts = sorted(daily_all["account"].unique().tolist()) if len(daily_all) else []
    account = st.selectbox("アカウント", accounts) if accounts else ""
    cur_id = None
    if account:
        months = sorted(pd.to_datetime(daily_all.loc[daily_all["account"] == account, "date"]).dt.strftime("%Y-%m").unique(), reverse=True)
        cur_id = st.selectbox("今回の月", months, format_func=lambda k: f"{k[:4]}年{int(k[5:])}月")
    page = st.radio("メニュー", PAGES)


@st.cache_data(show_spinner=False)
def _build(client_id_, client_name_, account_, cur_id_, fingerprint):
    return analysis.build_analysis(client_name_, db.daily_df(client_id_, account_), db.demographics_df(client_id_, account_),
                                   db.meetings_df(client_id_), cur_id_, account_)


NEEDS_DATA = page in PAGES[:1] + PAGES[3:11]
A = None
if NEEDS_DATA:
    if not account:
        st.info("まだデータがありません。「➕ 新しいデータを追加」からファイルを入れてください。")
        st.stop()
    dm = db.meetings_df(client_id)
    fp = (len(daily_all), float(daily_all.drop(columns=["id", "client_id", "sns", "account", "date"]).sum().sum()), len(dm), len(db.demographics_df(client_id)),
          "|".join(dm["decided"].tolist() + dm["next_actions"].tolist()))
    A = _build(client_id, client_name, account, cur_id, fp)

# ------------------------------------------------------------ 各ページ
if page == PAGES[0]:
    st.header(f"{client_name} の SNS まとめ")
    st.caption(f"Instagram / @{A['account']} / 対象期間 {A['period']}(全{A['n_periods']}か月分のデータ)")
    show(report.render_section("summary", A) + report.render_section("changes", A) + report.render_section("follower", A)
         + report.render_section("data_notes", A))

elif page == PAGES[1]:
    st.header("新しいデータを追加")
    st.caption("追加したデータは、過去のデータを消さずにたまっていきます。「*」は必須です。空欄にした項目は「データなし」になります。")
    tabs = st.tabs(["① ファイルで追加(おすすめ)", "② 1日ぶんを手入力", "③ 会議メモ"])
    with tabs[0]:
        st.write("Instagramのインサイトから書き出した **Excel / CSV を、まとめて** 選んでください(複数ファイルOK)。"
                 "種類・アカウント名・期間は、ファイルの中身とファイル名から自動で見分けます。")
        st.markdown("対応しているファイル: " + " / ".join(importer.KIND_LABEL.values()))
        ups = st.file_uploader("ファイルを選ぶ(複数可)", type=["xlsx", "xls", "csv"], accept_multiple_files=True)
        mode = st.radio("同じ日・同じ期間の数字が既にあるとき", ["今ある数字は変えない(空欄だけ埋める)", "ファイルの数字で上書きする"], key="imp_mode")
        if ups:
            plans = []
            for i, up in enumerate(ups):
                p = importer.plan_file(up.name, up.getvalue())
                with st.expander(f"📄 {up.name}", expanded=True):
                    if p["df"] is None:
                        st.error(p["error"])
                        continue
                    kinds = list(importer.KIND_LABEL)
                    c1, c2 = st.columns(2)
                    kind = c1.selectbox("種類", kinds, index=kinds.index(p["kind"]) if p["kind"] else 0, format_func=importer.KIND_LABEL.get, key=f"k{i}")
                    acc = c2.text_input("アカウント名 *", value=p["account"] or account, key=f"a{i}", help="→ Instagramのユーザー名(@の後ろ)")
                    if kind in ("age", "gender"):
                        d1, d2 = st.columns(2)
                        s_ = d1.date_input("期間の開始日 *", value=date.fromisoformat(p["start"]) if p["start"] else date.today().replace(day=1), key=f"s{i}")
                        e_ = d2.date_input("期間の終了日 *", value=date.fromisoformat(p["end"]) if p["end"] else date.today(), key=f"e{i}")
                    else:
                        s_ = e_ = None
                        rows, errs, ign = importer.convert_daily(p["df"])
                        if rows:
                            st.write(f"読み取れた日: **{len(rows)}日分**({rows[0]['date']}〜{rows[-1]['date']}) / エラー: **{len(errs)}行**")
                        for e in errs[:10]:
                            st.error(e)
                        if ign:
                            st.caption("読み取らなかった列: " + "、".join(ign) + "(この分析では使わない列です)")
                    st.dataframe(p["df"].head(5), hide_index=True, width="stretch")
                    plans.append((p, acc.strip(), kind, s_, e_))
            if plans and st.button(f"{len(plans)}ファイルを取り込む", type="primary", key="imp_btn"):
                cid = client_id
                for p, acc, kind, s_, e_ in plans:
                    if not acc:
                        st.error(f"{p['name']}: アカウント名を入力してください。")
                        continue
                    msg = importer.import_plan(db, cid, p, acc, kind, s_.isoformat() if s_ else None, e_.isoformat() if e_ else None, mode.startswith("ファイル"))
                    st.write(f"・{p['name']}({importer.KIND_LABEL[kind]}): {msg}")
                st.success("取り込みが終わりました。左のメニューから、まとめを見られます。")
    with tabs[1]:
        st.info("通常は「① ファイルで追加」を使います。ここは、数字を1日ぶんだけ直接入れたいときの入口です。")
        c1, c2 = st.columns(2)
        dd = c1.date_input("日付 *", value=date.today(), key="d_date")
        acc_in = c2.text_input("アカウント名 *", value=account or "", placeholder="例: sample_account", key="d_acc", help="→ Instagramのユーザー名(@の後ろ)")
        vals, errs = {}, []
        cols = st.columns(3)
        for i, (k, lab, ex, hlp) in enumerate(NUM_FIELDS):
            with cols[i % 3]:
                txt = st.text_input(lab + (" *" if k == "followers" else ""), key=f"d_{k}", placeholder=ex, help="→ " + hlp)
            vals[k], e = parse_num(txt, lab, k == "followers", allow_negative=k in ("follower_net", "follows_change"))
            if e:
                errs.append(e)
        st.write("その日に投稿した本数")
        cols = st.columns(5)
        for i, (k, lab, ex, hlp) in enumerate(COUNT_FIELDS):
            vals[k] = cols[i].number_input(lab, min_value=0, step=1, key=f"d_{k}", help="→ " + hlp)
        over = st.checkbox("同じ日のデータが既にあるときは、上書きする", key="d_over")
        if st.button("この内容で追加", type="primary", key="d_btn"):
            if not acc_in.strip():
                errs.append("「アカウント名」は必須です。")
            if errs:
                for e in errs:
                    st.error(e)
            else:
                r = db.upsert_daily(client_id, acc_in.strip(), [dict(date=dd.isoformat(), **vals)], over)
                st.success("追加しました。" if r["inserted"] else "数字を更新しました。" if r["updated"] else "変化はありませんでした(同じ日の数字が既にあります。上書きするときはチェックを入れてください)。")
    with tabs[2]:
        md_ = st.date_input("会議の日", value=date.today(), key="mt_d")
        decided = st.text_area("今回決まったこと", placeholder="例: 来月は週2回、投稿する", key="mt_dec")
        nxt = st.text_area("次にやること", placeholder="例: プロフィールのリンクの文言を直す(担当: 〇〇)", key="mt_next")
        if st.button("会議メモを保存", type="primary", key="mt_btn"):
            if not (decided.strip() or nxt.strip()):
                st.error("「決まったこと」か「次にやること」のどちらかは入力してください。")
            else:
                db.add_meeting(client_id, md_.isoformat(), decided.strip(), nxt.strip())
                st.success("保存しました。")

elif page == PAGES[2]:
    st.header("データの確認・修正・削除")
    st.caption("表の数字を直して「変更を保存」を押すと直ります。「削除」にチェックを入れて保存すると消えます(元には戻せません)。")
    tabs = st.tabs(["日ごとの数字", "フォロワーの年齢・性別", "会議メモ"])

    def editor(df, table, cols, cfg, key, updater, disabled=()):
        if df.empty:
            st.info("データがまだありません。")
            return
        d = df[["id"] + cols].copy()
        d.insert(1, "削除", False)
        ed = st.data_editor(d, column_config=cfg, disabled=["id", *disabled], hide_index=True, width="stretch", key=key)
        ok = st.checkbox("削除にチェックした行を、本当に削除する", key=key + "_ok")
        if st.button("変更を保存", type="primary", key=key + "_btn"):
            changed, dels = diff_edits(d, ed)
            if dels and not ok:
                st.error("削除するときは「本当に削除する」にもチェックを入れてください。")
                return
            for row in changed:
                updater(row)
            if dels:
                db.delete_rows(table, dels)
            if changed or dels:
                st.session_state["edit_msg"] = f"修正 {len(changed)}件 / 削除 {len(dels)}件 を保存しました。"
                st.rerun()
            st.info("変更はありませんでした。")

    if st.session_state.get("edit_msg"):
        st.success(st.session_state.pop("edit_msg"))
    with tabs[0]:
        ddf = db.daily_df(client_id, account) if account else pd.DataFrame()
        cfg = {"date": "日付", **{k: st.column_config.NumberColumn(lab, help="→ " + hlp) for k, lab, _, hlp in DAILY_FIELDS}}
        editor(ddf, "daily", ["date"] + db.DAILY_COLS, cfg, "ed_d",
               lambda b: db.update_daily(int(b["id"]), {k: (None if pd.isna(b[k]) else b[k]) for k in b.index}))
    with tabs[1]:
        gdf = db.demographics_df(client_id, account) if account else pd.DataFrame()
        editor(gdf, "demographics", ["period_start", "period_end", "kind", "grp", "female_pct", "female_n", "male_pct", "male_n"],
               {"period_start": "開始日", "period_end": "終了日", "kind": "種類(age=年齢/gender=性別)", "grp": "区分", "female_pct": "女性(%)",
                "female_n": "女性(人)", "male_pct": "男性(%)", "male_n": "男性(人)"}, "ed_g", lambda b: None,
               disabled=["period_start", "period_end", "kind", "grp", "female_pct", "female_n", "male_pct", "male_n"])
        st.caption("年齢・性別は、直すときは削除してから、ファイルをもう一度取り込んでください。")
    with tabs[2]:
        mdf = db.meetings_df(client_id)
        editor(mdf, "meetings", ["meeting_date", "decided", "next_actions"],
               {"meeting_date": "会議の日", "decided": "決まったこと", "next_actions": "次にやること"}, "ed_m",
               lambda b: db.update_meeting(int(b["id"]), b["meeting_date"], b["decided"] or "", b["next_actions"] or ""))

elif page in PAGES[3:8]:
    show(report.render_section("deep", A, A["deep"][PAGES.index(page) - 3]))

elif page == PAGES[8]:
    st.header("投稿した日の分析")
    show(report.render_section("posts", A) + report.render_section("breakdowns", A))

elif page == PAGES[9]:
    st.header("過去との比較")
    st.caption("「前回の会議」「1か月前」「3か月前」と比べています。比べる相手の月が無いときは「データなし」と出ます。")
    show(report.render_section("changes", A))
    S, G = A["monthly_df"], A["daily_df"]
    opts = {"end_followers": "フォロワー数(その日の終わり)", "follower_net": "フォロワー増減", "profile_views": "プロフィールアクセス",
            "link_taps": "リンククリック", "impressions": "インプレッション", "reach": "リーチ", "likes": "いいね", "comments": "コメント", "saves": "保存"}
    k = st.selectbox("日ごとの推移を見る項目", list(opts), format_func=opts.get)
    show(ch.line_chart([analysis.md(x) for x in G["dt"]], [(opts[k], [None if pd.isna(v) else float(v) for v in G[k]])], ch.fmt_int, opts[k] + "の推移"))
    if len(S) >= 2:
        mk = {"followers": "フォロワー数", "impressions": "インプレッション", "reach": "リーチ", "profile_visits": "プロフィールアクセス", "link_clicks": "リンククリック"}
        k2 = st.selectbox("月ごとの推移を見る項目", list(mk), format_func=mk.get)
        show(ch.line_chart([analysis.month_label(r) for _, r in S.iterrows()], [(mk[k2], [None if pd.isna(v) else float(v) for v in S[k2]])], ch.fmt_int, mk[k2] + "の月ごとの推移"))
    else:
        st.info("月ごとの推移は、2か月分のデータがたまると表示されます。")

elif page == PAGES[10]:
    st.header("分析ファイルを作る")
    st.write(f"対象: **{client_name}** / 期間 **{A['period']}**(左の「今回の月」で変えられます)")
    lab = st.text_input("ファイルにつける名前(省略できます)", placeholder="例: 10月定例会議", key="rep_label")
    if st.button("📄 分析ファイルを作る(Excel + HTML + PDF)", type="primary"):
        with st.spinner("作成中…(PDFは数秒かかります)"):
            res = report.create_files(client_id, A, lab.strip())
        st.success("作成しました。下のボタンからダウンロードできます。")
        if res["pdf_error"]:
            st.warning("PDFは作れませんでした。README の「PDFが作れないとき」を見てください。(" + res["pdf_error"] + ")")

    def dl(label, path, mime, key):
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                st.download_button(label, f.read(), file_name=os.path.basename(path), mime=mime, key=key)

    MIMES = [("PDF", "pdf_path", "application/pdf"), ("HTML", "html_path", "text/html"),
             ("Excel", "xlsx_path", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")]
    st.subheader("これまでに作った分析ファイル")
    rdf = db.reports_df(client_id)
    if rdf.empty:
        st.caption("まだありません。")
    for r in rdf.itertuples():
        c = st.columns([3, 1, 1, 1])
        c[0].write(f"**{r.created_at}** ／ 期間 {r.period_label} {('／ ' + r.label) if r.label else ''}")
        for col, (nm, attr, mime) in zip(c[1:], MIMES):
            with col:
                dl(nm, getattr(r, attr), mime, f"dl_{r.id}_{attr}")

elif page == PAGES[11]:
    st.header("用語集")
    st.caption("用語 → 意味 → 数字の見方(良い目安)")
    show("<style>" + report.CSS + "</style><div class='card'><div class='scroll'><table class='gl'><tr><th>用語</th><th>→ 意味</th><th>→ 数字の見方(良い目安)</th></tr>"
         + "".join(f"<tr><th class='l'>{t}</th><td>→ {m}</td><td>{g}</td></tr>" for t, m, g in GLOSSARY) + "</table></div></div>")

else:
    st.header("使い方")
    st.markdown("""
### 毎回の会議の流れ(3ステップ)
```
①  ➕新しいデータを追加   →   ②  🏠ホームで確認(深掘りページで説明)   →   ③  📄分析ファイルを作る
   (インサイトのファイルを       (矢印と色で良し悪しが分かる)            (PDF・HTML・Excel)
    まとめて選ぶ)
```
1. **新しいデータを追加**: 「ファイルで追加」で、Instagramインサイトのファイル(フォロワー・エンゲージメント・プロフィール・年齢・性別)をまとめて選びます。会議メモもここで残せます。
2. **画面を共有して説明**: 「ホーム」で今回のまとめ、「深掘り」の5ページで1つずつ説明します。
3. **分析ファイルを作る**: ボタン1つで PDF・HTML・Excel が作られ、その場でダウンロードできます。過去のファイルも一覧から再ダウンロードできます。

### 色と矢印の見方
<span style="color:#2f855a;font-weight:700">↑ 増えた(緑)</span> ／ <span style="color:#c53030;font-weight:700">↓ 減った(赤)</span> ／ <span style="color:#718096;font-weight:700">→ ほぼ同じ(灰色)</span> ／ – データなし

### 困ったとき
- 間違えて入れた → 「🛠 データの確認・修正・削除」で直せます。
- 数字がない項目 → 「データなし」と出ます(推測では埋めません)。
- 言葉が分からない → 「📖 用語集」を見てください。
詳しくは README.md を見てください。
""", unsafe_allow_html=True)
