"""タイトル正規化: 型番・容量・色を抽出して product_key を作る。"""
from __future__ import annotations

import re
import unicodedata

COLORS = {
    "black": ["black", "ブラック", "黒", "スペースグレイ", "スペースグレー", "space gray", "space grey"],
    "white": ["white", "ホワイト", "白", "シルバー", "silver"],
    "red": ["red", "レッド", "赤"],
    "blue": ["blue", "ブルー", "青", "ネオンブルー"],
    "pink": ["pink", "ピンク", "ネオンピンク"],
    "green": ["green", "グリーン", "緑"],
    "gold": ["gold", "ゴールド", "金"],
    "yellow": ["yellow", "イエロー", "黄"],
    "purple": ["purple", "パープル", "紫"],
    "gray": ["gray", "grey", "グレー", "グレイ", "灰"],
}
NOISE = [
    "送料無料", "送料込み", "送料込", "美品", "新品", "未使用", "未開封", "中古", "即購入可", "即購入ok",
    "即決", "匿名配送", "箱付き", "箱あり", "付属品完備", "完備", "simフリー", "sim free", "simfree",
    "訳あり", "セット", "本体", "国内正規品", "正規品", "動作確認済み", "動作確認済", "動作品", "です",
]
_COLOR_LOOKUP = sorted(
    ((alias, canon) for canon, aliases in COLORS.items() for alias in aliases),
    key=lambda x: -len(x[0]),
)
_CAP_RE = re.compile(r"(?<![a-z0-9])(\d{1,4})\s*(gb|tb)(?![a-z])")
_JOIN_RE = re.compile(r"(?<![a-z0-9])([a-z]{2,})[\s\-]?(\d{1,3})(?![a-z0-9])")
_MODEL_RE = re.compile(r"(?<![a-z0-9])(?:[a-z]+-?\d+[a-z0-9]*(?:-[a-z0-9]+)*|\d+[a-z]+\d*[a-z0-9]*)(?![a-z0-9])")
_UNITS = {"4k", "5g", "3d", "8k", "2k", "4g", "3g"}
_BRACKETS = re.compile(r"[【】\[\]()（）「」『』★☆◆◇■□●○※!！?？/／,、。~〜]")


def _extract_capacity(text: str) -> tuple[str, str]:
    m = _CAP_RE.search(text)
    if not m:
        return text, ""
    cap = f"{int(m.group(1))}{m.group(2)}"
    return text[: m.start()] + " " + text[m.end():], cap


def _extract_color(text: str) -> tuple[str, str]:
    for alias, canon in _COLOR_LOOKUP:
        if re.fullmatch(r"[a-z ]+", alias):
            pat = rf"(?<![a-z]){re.escape(alias)}(?![a-z])"
        else:
            pat = re.escape(alias)
        if re.search(pat, text):
            return re.sub(pat, " ", text), canon
    return text, ""


def parse_title(title: str) -> dict:
    t = unicodedata.normalize("NFKC", title).lower()
    t = _BRACKETS.sub(" ", t)
    for n in sorted(NOISE, key=len, reverse=True):
        t = t.replace(n, " ")
    t, capacity = _extract_capacity(t)
    t, color = _extract_color(t)
    t = _JOIN_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}", t)
    models = sorted({m for m in _MODEL_RE.findall(t) if m not in _UNITS})
    words = sorted({w for w in t.split() if len(w) >= 2 and w not in models})
    return {"models": models, "capacity": capacity, "color": color, "words": words}


def normalize_title(title: str) -> str:
    """同一商品判定用キー。型番があれば 型番+容量+色、無ければ単語+容量+色。"""
    p = parse_title(title)
    core = p["models"] if p["models"] else p["words"]
    parts = [*core, p["capacity"], p["color"]]
    return "|".join(x for x in parts if x)
