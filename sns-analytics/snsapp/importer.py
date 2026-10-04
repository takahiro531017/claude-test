"""インサイトのCSV/Excel取り込み。列名のゆれを吸収し、足りない列は画面で選べるようにする。"""
import io
import re

import pandas as pd

from .db import POST_NUM, SNAP_NUM

ACCOUNT_FIELDS = {
    "period_start": "開始日", "period_end": "終了日", "account": "アカウント名", "followers": "フォロワー数",
    "impressions": "インプレッション", "reach": "リーチ", "likes": "いいね", "comments": "コメント", "saves": "保存",
    "shares": "シェア", "profile_visits": "プロフィールアクセス", "link_clicks": "リンククリック",
}
POST_FIELDS = {
    "posted_at": "投稿日時", "post_type": "投稿タイプ", "theme": "テーマ", "caption": "キャプション(説明文)",
    "impressions": "インプレッション", "reach": "リーチ", "likes": "いいね", "comments": "コメント", "saves": "保存",
    "shares": "シェア", "profile_visits": "プロフィールアクセス", "link_clicks": "リンククリック",
}
ACCOUNT_REQUIRED = ["period_start", "period_end", "followers", "impressions", "reach"]
POST_REQUIRED = ["posted_at", "post_type", "reach"]

ALIASES = {
    "period_start": ["開始日", "期間開始", "期間の開始", "periodstart", "startdate", "start", "from"],
    "period_end": ["終了日", "期間終了", "期間の終了", "periodend", "enddate", "end", "to"],
    "account": ["アカウント名", "アカウント", "account", "accountname", "username", "ユーザー名"],
    "followers": ["フォロワー数", "フォロワー", "followers", "followercount"],
    "impressions": ["インプレッション", "インプレッション数", "表示", "表示回数", "impressions", "views", "閲覧数", "視聴数"],
    "reach": ["リーチ", "リーチ数", "reach"],
    "likes": ["いいね", "いいね!", "いいね数", "likes", "like"],
    "comments": ["コメント", "コメント数", "comments", "comment"],
    "saves": ["保存", "保存数", "saves", "save", "saved"],
    "shares": ["シェア", "シェア数", "共有", "shares", "share"],
    "profile_visits": ["プロフィールアクセス", "プロフィールへのアクセス", "プロフィールアクセス数", "プロフィールの表示",
                       "profilevisits", "profileviews"],
    "link_clicks": ["リンククリック", "リンクのクリック", "リンククリック数", "ウェブサイトのクリック", "linkclicks",
                    "websiteclicks", "linkclick"],
    "posted_at": ["投稿日時", "公開日時", "投稿日", "公開日", "日付", "日時", "publishtime", "posttime", "date", "publishedat", "posteddate"],
    "post_type": ["投稿タイプ", "投稿の種類", "種類", "タイプ", "posttype", "type", "mediatype"],
    "theme": ["テーマ", "カテゴリ", "カテゴリー", "theme", "category", "topic"],
    "caption": ["キャプション", "説明", "説明文", "タイトル", "description", "caption", "title"],
}


def _norm(s) -> str:
    return re.sub(r"[\s_\-　()（）]", "", str(s)).lower()


def read_table(name: str, raw: bytes) -> pd.DataFrame:
    if name.lower().endswith((".xlsx", ".xlsm", ".xls")):
        df = pd.read_excel(io.BytesIO(raw))
    else:
        for enc in ("utf-8-sig", "cp932", "utf-16"):
            try:
                df = pd.read_csv(io.BytesIO(raw), encoding=enc, sep=None, engine="python")
                break
            except Exception:
                df = None
        if df is None:
            raise ValueError("ファイルを読めませんでした。CSV(文字コードUTF-8かShift_JIS)またはExcelで保存し直してください。")
    df.columns = [str(c).strip() for c in df.columns]
    return df.dropna(how="all")


def guess_mapping(df: pd.DataFrame, fields) -> dict:
    """項目名 → ファイルの列名(見つからなければ None)"""
    cols = {_norm(c): c for c in df.columns}
    out, used = {}, set()
    for f in fields:
        out[f] = None
        for a in ALIASES.get(f, []):
            c = cols.get(_norm(a))
            if c is not None and c not in used:
                out[f], _ = c, used.add(c)
                break
    return out


def _to_num(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ("", "-", "—", "nan", "None"):
        return None
    s = str(v).replace(",", "").replace("，", "").replace("人", "").replace("回", "").strip()
    try:
        return float(s)
    except ValueError:
        raise ValueError(f"数字ではありません: 「{v}」")


def _to_date(v):
    d = pd.to_datetime(v, errors="coerce")
    if pd.isna(d):
        raise ValueError(f"日付として読めません: 「{v}」")
    return d


def normalize_post_type(v) -> str:
    s = str(v).strip().lower()
    if any(k in s for k in ("story", "stories", "ストーリー")):
        return "ストーリーズ"
    if any(k in s for k in ("reel", "リール")):
        return "リール"
    if any(k in s for k in ("video", "動画")):
        return "動画"
    if any(k in s for k in ("image", "photo", "carousel", "画像", "写真", "フォト", "カルーセル", "フィード")):
        return "画像"
    raise ValueError(f"投稿タイプが分かりません: 「{v}」(画像/動画/リール/ストーリーズのどれか)")


def convert(df: pd.DataFrame, mapping: dict, kind: str, defaults: dict | None = None):
    """df → (正しい行のリスト, エラー文のリスト)。kind は 'account' か 'post'。"""
    defaults = defaults or {}
    req = ACCOUNT_REQUIRED if kind == "account" else POST_REQUIRED
    nums = SNAP_NUM if kind == "account" else POST_NUM
    ok, errors = [], []
    for i, row in df.iterrows():
        line = i + 2  # 見出し行ぶん
        rec = {}
        try:
            for f, col in mapping.items():
                v = row[col] if col else None
                if f in nums:
                    rec[f] = _to_num(v)
                elif f in ("period_start", "period_end"):
                    rec[f] = _to_date(v).date().isoformat() if col else None
                elif f == "posted_at":
                    d = _to_date(v)
                    has_time = isinstance(v, str) and re.search(r"\d{1,2}:\d{2}", v) or (not isinstance(v, str) and (d.hour or d.minute))
                    rec[f] = d.strftime("%Y-%m-%d %H:%M") if has_time else d.strftime("%Y-%m-%d")
                elif f == "post_type":
                    rec[f] = normalize_post_type(v) if col else None
                else:
                    rec[f] = "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()
            for k, dv in defaults.items():
                if not rec.get(k):
                    rec[k] = dv
            missing = [k for k in req if rec.get(k) in (None, "")]
            if kind == "account" and not rec.get("account"):
                missing.append("account")
            if missing:
                names = ACCOUNT_FIELDS if kind == "account" else POST_FIELDS
                raise ValueError("必須の項目が空です: " + "、".join(names[m] for m in missing))
            if any(rec.get(k) is not None and rec[k] < 0 for k in nums):
                raise ValueError("マイナスの数字があります")
            if kind == "account" and rec["period_start"] > rec["period_end"]:
                raise ValueError("開始日が終了日より後になっています")
            ok.append(rec)
        except Exception as e:  # noqa: BLE001 — 行ごとのエラーを利用者に見せる
            errors.append(f"{line}行目: {e}")
    return ok, errors
