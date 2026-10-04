"""インサイトのExcel/CSVの取り込み。5種類(フォロワー・エンゲージメント・プロフィール・年齢・性別)を列名から自動で見分ける。"""
import io
import re

import pandas as pd

from .db import COUNT_COLS, DAILY_COLS

KIND_LABEL = {
    "followers": "フォロワーの推移(日ごと)", "engagement": "投稿の反応の推移(日ごと)", "profile": "プロフィールの動き(日ごと)",
    "age": "フォロワーの年齢", "gender": "フォロワーの性別",
}

# 日ごとの数字: DB列名 → 列名のゆれ
ALIASES = {
    "date": ["日付", "日", "date", "day"],
    "followers": ["フォロワー数", "フォロワー", "followers", "followercount"],
    "follower_net": ["トータルフォロワー増減", "フォロワー増減", "フォロワー増加数", "followerchange", "netfollowers"],
    "new_followers": ["新規フォロワー増数", "新規フォロワー数", "新規フォロワー", "newfollowers"],
    "follows": ["フォロー数", "following"],
    "follows_change": ["フォロー増減"],
    "impressions": ["インプレッション", "インプレッション数", "表示回数", "表示", "impressions", "views"],
    "reach": ["リーチ", "リーチ数", "reach"],
    "likes": ["いいね", "いいね!", "いいね数", "likes"],
    "comments": ["コメント", "コメント数", "comments"],
    "saves": ["保存数", "保存", "saves"],
    "shares": ["シェア数", "シェア", "共有", "shares"],
    "video_views": ["動画再生", "動画再生数", "再生数", "videoviews", "plays"],
    "profile_views": ["プロフィールビュー数", "プロフィールビュー", "プロフィールアクセス", "プロフィールへのアクセス", "profileviews", "profilevisits"],
    "website_taps": ["ウェブサイトタップ数", "ウェブサイトのタップ", "リンククリック", "websitetaps", "linkclicks"],
    "text_link_taps": ["テキスト内リンクタップ数", "テキストリンクタップ数"],
    "email_taps": ["メールタップ数", "メールのタップ"],
    "phone_taps": ["電話番号タップ数", "電話のタップ"],
    "direction_taps": ["道順タップ数", "道順のタップ"],
    "posts_image": ["画像投稿数"], "posts_carousel": ["カルーセル投稿数"], "posts_reel": ["リール投稿数"],
    "posts_video": ["動画投稿数"], "posts_story": ["ストーリーズ投稿数", "ストーリー投稿数"],
}
FILE_RE = re.compile(r"([A-Za-z0-9._]+)_(\d{8})-(\d{8})")


def _norm(s) -> str:
    return re.sub(r"[\s_\-　()（）]", "", str(s)).lower()


def read_table(name: str, raw: bytes) -> pd.DataFrame:
    if name.lower().endswith((".xlsx", ".xlsm", ".xls")):
        df = pd.read_excel(io.BytesIO(raw))
    else:
        df = None
        for enc in ("utf-8-sig", "cp932", "utf-16"):
            try:
                df = pd.read_csv(io.BytesIO(raw), encoding=enc, sep=None, engine="python")
                break
            except Exception:
                continue
        if df is None:
            raise ValueError("ファイルを読めませんでした。CSV(UTF-8かShift_JIS)またはExcelで保存し直してください。")
    df.columns = [str(c).strip() for c in df.columns]
    return df.dropna(how="all")


def detect_kind(df: pd.DataFrame):
    cols = {_norm(c) for c in df.columns}
    has = lambda *names: any(_norm(n) in cols for n in names)
    if has("年齢"):
        return "age"
    if has("日付", "date"):
        if has("フォロワー数", "followers"):
            return "followers"
        if has("インプレッション", "リーチ", "impressions", "reach"):
            return "engagement"
        if has("プロフィールビュー数", "profileviews", "プロフィールアクセス"):
            return "profile"
    if has("女性(%)", "女性(人)") and not has("日付"):
        return "gender"
    return None


def parse_filename(name: str):
    """ファイル名の「アカウント名_開始日-終了日」から (アカウント, 開始日, 終了日) を取り出す。無ければ None。"""
    m = None
    for m in FILE_RE.finditer(name):
        pass
    if not m:
        return None, None, None
    f = lambda s: f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return m.group(1).strip("_"), f(m.group(2)), f(m.group(3))


def _to_num(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ("", "-", "—", "nan", "None"):
        return None
    try:
        return float(str(v).replace(",", "").replace("，", "").replace("%", "").strip())
    except ValueError:
        raise ValueError(f"数字ではありません: 「{v}」")


def convert_daily(df: pd.DataFrame):
    """日ごとの表 → (行のリスト, エラー文のリスト, 読み取らなかった列名)。空欄は「データなし」(None)。投稿数の空欄だけは0本。"""
    cols = {_norm(c): c for c in df.columns}
    mapping, used = {}, set()
    for f, names in ALIASES.items():
        for n in names:
            c = cols.get(_norm(n))
            if c is not None and c not in used:
                mapping[f], _ = c, used.add(c)
                break
    ignored = [c for c in df.columns if c not in used]
    rows, errors = [], []
    for i, row in df.iterrows():
        try:
            d = pd.to_datetime(row[mapping["date"]], errors="coerce")
            if pd.isna(d):
                raise ValueError(f"日付として読めません: 「{row[mapping['date']]}」")
            rec = {"date": d.date().isoformat()}
            for f in DAILY_COLS:
                if f in mapping:
                    v = _to_num(row[mapping[f]])
                    if v is None and f in COUNT_COLS:
                        v = 0.0
                    if v is not None and v < 0 and f not in ("follower_net", "follows_change"):
                        raise ValueError(f"「{mapping[f]}」にマイナスの数字があります")
                    rec[f] = v
            rows.append(rec)
        except Exception as e:  # noqa: BLE001 — 行ごとのエラーを利用者に見せる
            errors.append(f"{i + 2}行目: {e}")
    return rows, errors, ignored


def convert_demographics(df: pd.DataFrame, kind: str):
    """年齢・性別の表 → (行のリスト, エラー文のリスト)"""
    cols = {_norm(c): c for c in df.columns}
    get = lambda *n: next((cols[_norm(x)] for x in n if _norm(x) in cols), None)
    fp, fn, mp, mn = get("女性(%)"), get("女性(人)"), get("男性(%)"), get("男性(人)")
    ag = get("年齢")
    rows, errors = [], []
    if (kind == "age" and not ag) or not (fn and mn):
        return [], ["「年齢」「女性(人)」「男性(人)」の列が見つかりません。"]
    for i, r in df.iterrows():
        try:
            rows.append(dict(grp=str(r[ag]).strip() if kind == "age" else "全体",
                             female_pct=_to_num(r[fp]) if fp else None, female_n=_to_num(r[fn]),
                             male_pct=_to_num(r[mp]) if mp else None, male_n=_to_num(r[mn])))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{i + 2}行目: {e}")
    return rows, errors


def plan_file(name: str, raw: bytes) -> dict:
    """1ファイルを読み、種類・アカウント・期間を見分ける。読めないときは error に理由が入る。"""
    out = dict(name=name, df=None, kind=None, account=None, start=None, end=None, error=None)
    try:
        out["df"] = read_table(name, raw)
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)
        return out
    out["kind"] = detect_kind(out["df"])
    out["account"], out["start"], out["end"] = parse_filename(name)
    if out["kind"] is None:
        out["error"] = "どの種類のファイルか分かりませんでした。右の「種類」から選んでください。"
    return out


def import_plan(db, client_id, plan: dict, account: str, kind: str, start: str, end: str, overwrite: bool) -> str:
    """1ファイルをDBに入れる。戻り値は画面に出す結果の文章。"""
    df = plan["df"]
    if kind in ("followers", "engagement", "profile"):
        rows, errs, _ = convert_daily(df)
        if errs:
            return "取り込めませんでした: " + errs[0]
        r = db.upsert_daily(client_id, account, rows, overwrite)
        return f"新しい日 {r['inserted']}日 / 数字を追加・更新した日 {r['updated']}日 / 変化なし {r['unchanged']}日"
    rows, errs = convert_demographics(df, kind)
    if errs:
        return "取り込めませんでした: " + errs[0]
    res = db.save_demographics(client_id, account, kind, start, end, rows, overwrite)
    return {"inserted": "追加しました", "updated": "入れ替えました", "skipped": "同じ期間のデータが既にあるため、飛ばしました(上書きにチェックすると入れ替えます)"}[res]
