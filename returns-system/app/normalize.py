"""表記ゆれを吸収するための正規化。保存時に必ず通す。"""
import re
import unicodedata

_SPACES = re.compile(r"\s+")
# 品番で同一視するハイフン・区切り類(NFKC後)
_PART_SEPARATORS = re.compile(r"[\s\-‐-―−ー⁃_/\\.・]+")


def clean_display(text: str | None) -> str:
    """画面に表示する名前。全角英数→半角、前後空白除去、連続空白を1つに。"""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    return _SPACES.sub(" ", t).strip()


def norm_key(text: str | None) -> str:
    """名前の重複判定用キー。大文字小文字・空白の差を無視。"""
    return clean_display(text).casefold().replace(" ", "")


def part_key(text: str | None) -> str:
    """品番用キー。ハイフン・空白・スラッシュ等の違いも吸収する。"""
    t = clean_display(text).casefold()
    return _PART_SEPARATORS.sub("", t)
