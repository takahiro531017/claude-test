from __future__ import annotations

import unicodedata

from ..config import ExcludeConfig
from ..models import Item


def _n(s: str) -> str:
    return unicodedata.normalize("NFKC", s).lower()


def check_exclusion(item: Item, cfg: ExcludeConfig) -> str | None:
    """除外理由を返す。除外対象でなければ None。"""
    text = _n(f"{item.title} {item.description}")
    cat = _n(item.category)
    groups = [
        ("ジャンク/動作未確認", cfg.keywords_junk),
        ("偽物疑い", cfg.keywords_fake),
        ("ブランド品(真贋リスク)", cfg.brands),
        ("NGワード", cfg.ng_words),
    ]
    for label, words in groups:
        for w in words:
            if w and _n(w) in text:
                return f"{label}: {w}"
    for w in cfg.categories:
        if w and (_n(w) in cat or _n(w) in text):
            return f"転売禁止カテゴリ: {w}"
    return None
