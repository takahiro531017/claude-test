"""SNS運用代行 分析アプリ(Instagram)。起動: streamlit run app.py"""
import os
from datetime import date, datetime, time

import pandas as pd
import streamlit as st

from snsapp import analysis, db, importer, report, sample_data
from snsapp import charts as ch
from snsapp.db import POST_NUM, POST_TYPES, SNAP_NUM, diff_edits
from snsapp.glossary import GLOSSARY

st.set_page_config(page_title="SNS分析アプリ", page_icon="📊", layout="wide")
sample_data.seed_if_empty()

NUM_LABELS = {"followers": "フォロワー数", "impressions": "インプレッション", "reach": "リーチ", "likes": "いいね", "comments": "コメント",
              "saves": "保存", "shares": "シェア", "profile_visits": "プロフィールアクセス", "link_clicks": "リンククリック"}
NUM_HELP = {"followers": "フォローしている人の数", "impressions": "画面に表示された回数(見られた回数)", "reach": "投稿を見た「人」の数",
            "likes": "いいねの回数", "comments": "コメントの数", "saves": "保存された回数", "shares": "シェアされた回数",
            "profile_visits": "プロフィールを開いた回数", "link_clicks": "プロフィールのリンクを押した回数"}
EXAMPLES = {"followers": "例: 12500", "impressions": "例: 69885", "reach": "例: 33678", "likes": "例: 2052", "comments": "例: 162",
            "saves": "例: 738", "shares": "例: 298", "profile_visits": "例: 1030", "link_clicks": "例: 168"}
REQUIRED_SNAP = ["followers", "impressions", "reach"]
REQUIRED_POST = ["reach"]


def show(html: str):
    st.html(html)


def parse_num(text, label, required):
    """入力欄の文字を数字にする。(値, エラー文)。空欄は「データなし」として保存。"""
    s = (text or "").strip().replace(",", "").replace("、", "")
    if not s:
        return None, (f"「{label}」は必須です。" if required else None)
    try:
        v = float(s)
    except ValueError:
        return None, f"「{label}」は数字で入力してください(例: 1250)。"
    if v < 0:
        return None, f"「{label}」にマイナスの数字は入れられません。"
    return v, None


def number_inputs(keys, required, prefix):
    vals, errs = {}, []
    cols = st.columns(3)
    for i, k in enumerate(keys):
        with cols[i % 3]:
            lab = NUM_LABELS[k] + (" *" if k in required else "")
            txt = st.text_input(lab, key=f"{prefix}_{k}", placeholder=EXAMPLES[k], help="→ " + NUM_HELP[k])
        vals[k], e = parse_num(txt, NUM_LABELS[k], k in required)
        if e:
            errs.append(e)
    return vals, errs


# ------------------------------------------------------------ サイドバー
db_clients = db.clients_df()
with st.sidebar:
    st.title("📊 SNS分析アプリ")
    names = db_clients["name"].tolist()
    client_name = st.selectbox("クライアント", names)
    client_id = int(db_clients.loc[db_clients["name"] == client_name, "id"].iloc[0])
    with st.expander("＋ クライアントを追加"):
        nn = st.text_input("会社名(新規)", key="new_client")
        if st.button("追加する") and nn.strip():
            try:
                db.add_client(nn)
                st.rerun()
            except Exception:
                st.error("同じ名前のクライアントが既にあります。")
    snaps_raw = db.snapshots_df(client_id)
    accounts = sorted(snaps_raw["account"].unique().tolist()) if len(snaps_raw) else []
    account = st.selectbox("アカウント", accounts) if accounts else ""
    cur_id = None
    if account:
        sa = snaps_raw[snaps_raw["account"] == account].sort_values("period_end")
        opts = {f"{r.period_start}〜{r.period_end}": int(r.id) for r in sa.itertuples()}
        pick = st.selectbox("今回の期間", list(opts)[::-1])
        cur_id = opts[pick]
    PAGES = ["🏠 ホーム(まとめ)", "➕ 新しいデータを追加", "🛠 データの確認・修正・削除", "🔎 深掘り:フォロワー", "🔎 深掘り:反応(エンゲージメント率)",
             "🔎 深掘り:リーチ・インプレッション", "🔎 深掘り:プロフィール・リンク", "🖼 投稿の分析", "⏪ 過去との比較", "📄 分析ファイルを作る", "📖 用語集", "❓ 使い方"]
    page = st.radio("メニュー", PAGES)
    st.caption("サンプルは架空のデータです。" if db_clients.loc[db_clients["name"] == client_name, "is_sample"].iloc[0] else "")


def get_analysis():
    if not account:
        return None
    return analysis.build_analysis(client_name, snaps_raw[snaps_raw["account"] == account], db.posts_df(client_id),
                                   db.meetings_df(client_id), cur_id, account)


A = get_analysis() if page not in ("➕ 新しいデータを追加", "🛠 データの確認・修正・削除", "📖 用語集", "❓ 使い方") else None
NEEDS_DATA = page in PAGES[:1] + PAGES[3:10]
if NEEDS_DATA and A is None:
    st.info("まだデータがありません。「➕ 新しいデータを追加」から数字を入れてください。")
    st.stop()

# ------------------------------------------------------------ 各ページ
if page == PAGES[0]:
    st.header(f"{client_name} の SNS まとめ")
    st.caption(f"Instagram / @{A['account']} / 対象期間 {A['period']}(全{A['n_periods']}期間のデータ)")
    show(report.render_section("summary", A) + report.render_section("changes", A))
    show(report.render_section("follower", A))

elif page == PAGES[1]:
    st.header("新しいデータを追加")
    st.caption("追加したデータは、過去のデータを消さずにたまっていきます。「*」は必須です。空欄にした項目は「データなし」になります。")
    tabs = st.tabs(["① 期間の数字", "② 投稿ごとの数字", "③ CSV/Excelで追加", "④ 会議メモ"])
    with tabs[0]:
        st.info("1行 = 1つの期間です。毎回「同じ長さの期間」(たとえば1か月ごと)で入れると、前回との比較が正しく見られます。")
        c1, c2, c3 = st.columns(3)
        ps = c1.date_input("期間の開始日 *", value=date.today().replace(day=1), key="snap_ps")
        pe = c2.date_input("期間の終了日 *", value=date.today(), key="snap_pe")
        acc_in = c3.text_input("アカウント名 *", value=account or "", placeholder="例: sample_cafe_official", key="snap_acc",
                               help="→ Instagramのユーザー名(@の後ろ)")
        st.text_input("SNSの種類", value="Instagram", disabled=True)
        vals, errs = number_inputs(SNAP_NUM, REQUIRED_SNAP, "snap")
        over = st.checkbox("同じ期間のデータが既にあるときは、上書きする", key="snap_over")
        if st.button("この内容で追加", type="primary", key="snap_btn"):
            if not acc_in.strip():
                errs.append("「アカウント名」は必須です。")
            if ps > pe:
                errs.append("開始日が終了日より後になっています。")
            if errs:
                for e in errs:
                    st.error(e)
            else:
                rec = dict(account=acc_in.strip(), period_start=ps.isoformat(), period_end=pe.isoformat(), **vals)
                r = db.save_snapshot(client_id, rec, over)
                if r == "skipped":
                    st.warning("同じ期間のデータが既にあります。上書きするときは、チェックを入れてもう一度押してください。")
                else:
                    st.success("追加しました。" if r == "inserted" else "上書きしました。")
    with tabs[1]:
        c1, c2, c3 = st.columns(3)
        pd_ = c1.date_input("投稿日 *", value=date.today(), key="post_d")
        known = c2.checkbox("投稿した時刻がわかる", value=True, key="post_known")
        pt = c2.time_input("投稿した時刻", value=time(19, 0), key="post_t", disabled=not known)
        ptype = c3.selectbox("投稿の種類 *", POST_TYPES, key="post_type")
        theme = st.text_input("テーマ", placeholder="例: 新商品 / スタッフ紹介 / お客様の声", key="post_theme")
        pv, perrs = number_inputs(POST_NUM, REQUIRED_POST, "post")
        pover = st.checkbox("同じ日時・種類の投稿が既にあるときは、上書きする", key="post_over")
        if st.button("この内容で追加", type="primary", key="post_btn"):
            if perrs:
                for e in perrs:
                    st.error(e)
            else:
                at = datetime.combine(pd_, pt).strftime("%Y-%m-%d %H:%M") if known else pd_.isoformat()
                r = db.save_post(client_id, dict(account=account or acc_in, posted_at=at, post_type=ptype, theme=theme.strip(), **pv), pover)
                st.warning("同じ投稿が既にあります。上書きするときはチェックを入れてください。") if r == "skipped" else st.success("追加しました。")
    with tabs[2]:
        st.write("Instagramのインサイト(Meta Business Suite)などで書き出した **CSV / Excel** を選んでください。")
        kind_lbl = st.radio("ファイルの中身", ["投稿ごとの数字(1行=1投稿)", "期間の数字(1行=1期間)"], horizontal=True)
        kind = "post" if kind_lbl.startswith("投稿") else "account"
        st.caption("サンプルのCSVは sample/ フォルダにあります(列名の例)。")
        up = st.file_uploader("ファイルを選ぶ", type=["csv", "xlsx", "xls"])
        if up:
            try:
                df = importer.read_table(up.name, up.getvalue())
            except Exception as e:
                st.error(str(e))
                st.stop()
            fields = importer.POST_FIELDS if kind == "post" else importer.ACCOUNT_FIELDS
            req = importer.POST_REQUIRED if kind == "post" else importer.ACCOUNT_REQUIRED
            guess = importer.guess_mapping(df, fields)
            st.subheader("列の対応づけ")
            st.caption("自動で見つけた対応です。違うときは選び直してください(「—」は「データなし」)。")
            mapping, cols = {}, st.columns(3)
            for i, (f, lab) in enumerate(fields.items()):
                choices = ["—"] + list(df.columns)
                dflt = choices.index(guess[f]) if guess[f] in choices else 0
                with cols[i % 3]:
                    sel = st.selectbox(lab + (" *" if f in req or (kind == "account" and f == "account") else ""), choices, index=dflt, key=f"map_{kind}_{f}")
                mapping[f] = None if sel == "—" else sel
            defaults = {}
            if kind == "account" and not mapping.get("account"):
                defaults["account"] = st.text_input("アカウント名(ファイルに無いとき) *", value=account or "", key="imp_acc")
            rows, errs = importer.convert(df, mapping, kind, defaults)
            st.subheader("取り込み前の確認")
            st.write(f"読み取れた行: **{len(rows)}行** / エラー: **{len(errs)}行**")
            for e in errs[:20]:
                st.error(e)
            if rows:
                prev = pd.DataFrame(rows)
                exists = [(db.snapshot_exists if kind == "account" else db.post_exists)(client_id, dict(r, sns="Instagram")) for r in rows]
                prev.insert(0, "状態", ["既にある" if x else "新規" for x in exists])
                st.dataframe(prev, width="stretch", hide_index=True)
                ow = st.checkbox(f"「既にある」{sum(exists)}行は上書きする(チェックしないと、飛ばします)", key="imp_over") if any(exists) else False
                if st.button(f"{len(rows)}行を追加する", type="primary", key="imp_btn"):
                    cnt = dict(inserted=0, updated=0, skipped=0)
                    for r in rows:
                        r = dict(r, sns="Instagram")
                        if kind == "post":
                            r.setdefault("account", account)
                        cnt[(db.save_snapshot if kind == "account" else db.save_post)(client_id, r, ow)] += 1
                    st.success(f"新規 {cnt['inserted']}行 / 上書き {cnt['updated']}行 / 飛ばした {cnt['skipped']}行")
    with tabs[3]:
        md = st.date_input("会議の日", value=date.today(), key="mt_d")
        decided = st.text_area("今回決まったこと", placeholder="例: 来月はリールを週2本にする", key="mt_dec")
        nxt = st.text_area("次にやること", placeholder="例: 豆知識の投稿を3本つくる(担当: 〇〇)", key="mt_next")
        if st.button("会議メモを保存", type="primary", key="mt_btn"):
            if not (decided.strip() or nxt.strip()):
                st.error("「決まったこと」か「次にやること」のどちらかは入力してください。")
            else:
                db.add_meeting(client_id, md.isoformat(), decided.strip(), nxt.strip())
                st.success("保存しました。")

elif page == PAGES[2]:
    st.header("データの確認・修正・削除")
    st.caption("表の数字を直して「変更を保存」を押すと直ります。「削除」にチェックを入れて保存すると消えます(元には戻せません)。")
    tabs = st.tabs(["期間の数字", "投稿ごとの数字", "会議メモ"])

    def editor(df, table, cols, cfg, key, updater):
        if df.empty:
            st.info("データがまだありません。")
            return
        d = df[["id"] + cols].copy()
        d.insert(1, "削除", False)
        ed = st.data_editor(d, column_config=cfg, disabled=["id"], hide_index=True, width="stretch", key=key)
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

    num_cfg = lambda keys: {k: st.column_config.NumberColumn(NUM_LABELS[k], min_value=0, help="→ " + NUM_HELP[k]) for k in keys}
    with tabs[0]:
        sdf = db.snapshots_df(client_id)
        editor(sdf, "snapshots", ["account", "period_start", "period_end"] + SNAP_NUM,
               {"account": "アカウント名", "period_start": "開始日", "period_end": "終了日", **num_cfg(SNAP_NUM)}, "ed_s",
               lambda b: db.update_snapshot(int(b["id"]), {k: (None if pd.isna(b[k]) else b[k]) for k in b.index}))
    with tabs[1]:
        pdf_ = db.posts_df(client_id)
        editor(pdf_, "posts", ["posted_at", "post_type", "theme"] + POST_NUM,
               {"posted_at": "投稿日時", "post_type": st.column_config.SelectboxColumn("種類", options=POST_TYPES),
                "theme": "テーマ", **num_cfg(POST_NUM)}, "ed_p",
               lambda b: db.update_post(int(b["id"]), {k: (None if pd.isna(b[k]) else b[k]) for k in b.index}))
    with tabs[2]:
        mdf = db.meetings_df(client_id)
        editor(mdf, "meetings", ["meeting_date", "decided", "next_actions"],
               {"meeting_date": "会議の日", "decided": "決まったこと", "next_actions": "次にやること"}, "ed_m",
               lambda b: db.update_meeting(int(b["id"]), b["meeting_date"], b["decided"] or "", b["next_actions"] or ""))

elif page in PAGES[3:7]:
    d = A["deep"][PAGES.index(page) - 3]
    show(report.render_section("deep", A, d))

elif page == PAGES[7]:
    st.header("投稿の分析")
    show(report.render_section("posts", A) + report.render_section("breakdowns", A))

elif page == PAGES[8]:
    st.header("過去との比較")
    st.caption("「前回の会議」「1か月前」「3か月前」と比べています。比べる相手の期間が見つからないときは「データなし」と出ます。")
    show(report.render_section("changes", A))
    key_names = {k: n for k, n, _ in analysis.METRICS}
    S = A["snaps_df"]
    k = st.selectbox("推移を見る項目", list(key_names), format_func=lambda x: key_names[x])
    kind = {kk: kd for kk, _, kd in analysis.METRICS}[k]
    labs = [analysis.label_of(r) for _, r in S.iterrows()]
    f = ch.fmt_pct if kind == "rate" else ch.fmt_int
    show(ch.line_chart(labs, [(key_names[k], [None if pd.isna(v) else float(v) for v in S[k]])], f, key_names[k] + "の推移"))

elif page == PAGES[9]:
    st.header("分析ファイルを作る")
    st.write(f"対象: **{client_name}** / 期間 **{A['period']}**(左の「今回の期間」で変えられます)")
    lab = st.text_input("ファイルにつける名前(省略できます)", placeholder="例: 10月定例会議", key="rep_label")
    if st.button("📄 分析ファイルを作る(Excel + HTML + PDF)", type="primary"):
        with st.spinner("作成中…(PDFは数秒かかります)"):
            res = report.create_files(client_id, A, lab.strip())
        st.session_state["last_report"] = {k: (str(v) if v else None) for k, v in res.items()}
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
                dl(f"{nm}", getattr(r, attr), mime, f"dl_{r.id}_{attr}")

elif page == PAGES[10]:
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
   (数字を入れる/CSV)          (矢印と色で良し悪しが分かる)            (PDF・HTML・Excel)
```
1. **新しいデータを追加**: 「期間の数字」と「投稿ごとの数字」を入力、またはインサイトのCSV/Excelをアップロードします。会議メモもここで残せます。
2. **画面を共有して説明**: 「ホーム」で今回のまとめ、「深掘り」の4ページで1つずつ説明します。
3. **分析ファイルを作る**: ボタン1つで PDF・HTML・Excel が作られ、その場でダウンロードできます。過去のファイルも一覧から再ダウンロードできます。

### 色と矢印の見方
<span style="color:#2f855a;font-weight:700">↑ 増えた(緑)</span> ／ <span style="color:#c53030;font-weight:700">↓ 減った(赤)</span> ／ <span style="color:#718096;font-weight:700">→ ほぼ同じ(灰色)</span> ／ – データなし

### 困ったとき
- 間違えて入れた → 「🛠 データの確認・修正・削除」で直せます。
- 数字が分からない項目 → 空欄にすると「データなし」になります(推測では埋めません)。
- 言葉が分からない → 「📖 用語集」を見てください。
詳しくは README.md を見てください。
""", unsafe_allow_html=True)
