"""伝票番号・日付・金額・メーカー名の正規化（比較用）。"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

_ZERO_RUN = re.compile(r"(?<![0-9])0+(?=[0-9])")


class Normalizer:
    """設定(normalize:)に従って伝票番号を比較用の文字列にする。"""

    def __init__(self, rules: dict | None = None):
        from shiire_check.config import DEFAULTS

        r = {**DEFAULTS["normalize"], **(rules or {})}
        self.nfkc = bool(r["nfkc"])
        self.upper = bool(r["uppercase"])
        self.remove_ws = bool(r["remove_whitespace"])
        self.zeros = bool(r["strip_leading_zeros"])
        chars = set()
        for c in r["remove_chars"] or []:
            chars.add(c)
            chars.add(unicodedata.normalize("NFKC", c))
        self.remove_chars = chars
        self.prefixes = [self._base(p) for p in (r["strip_prefixes"] or []) if p]
        self.prefixes.sort(key=len, reverse=True)

    def _base(self, s: str) -> str:
        if self.nfkc:
            s = unicodedata.normalize("NFKC", s)
        if self.upper:
            s = s.upper()
        return s.strip()

    def __call__(self, value) -> str:
        if value is None:
            return ""
        s = self._base(str(value))
        for p in self.prefixes:
            if s.startswith(p):
                s = s[len(p):].lstrip()
                break
        s = "".join(
            ch for ch in s
            if ch not in self.remove_chars and not (self.remove_ws and ch.isspace())
        )
        if self.zeros:
            s = _ZERO_RUN.sub("", s)
        return s


def parse_amount(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = unicodedata.normalize("NFKC", str(value))
    s = re.sub(r"[¥￥円,\s]", "", s)
    if not s:
        return None
    try:
        return float(Decimal(s))
    except InvalidOperation:
        return None


_ERA = {"令和": 2018, "R": 2018, "平成": 1988, "H": 1988, "昭和": 1925, "S": 1925}


def parse_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = unicodedata.normalize("NFKC", str(value)).strip()
    m = re.search(r"(令和|平成|昭和|[RHS])\s*(\d{1,2}|元)\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})", s)
    if m:
        y = 1 if m.group(2) == "元" else int(m.group(2))
        return _mk(_ERA[m.group(1)] + y, m.group(3), m.group(4))
    m = re.search(r"(\d{4})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})", s)
    if m:
        return _mk(int(m.group(1)), m.group(2), m.group(3))
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", s)
    if m:
        return _mk(int(m.group(1)), m.group(2), m.group(3))
    return None


def _mk(y, m, d) -> date | None:
    try:
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def dates_close(a: date, b: date, tolerance_days: int = 0) -> bool:
    return abs(a - b) <= timedelta(days=tolerance_days)


_COMPANY_WORDS = re.compile(r"株式会社|有限会社|合同会社|\(株\)|\(有\)|（株）|（有）|㈱|㈲")


def normalize_maker(value) -> str:
    if value is None:
        return ""
    s = unicodedata.normalize("NFKC", str(value))
    s = _COMPANY_WORDS.sub("", s)
    s = re.sub(r"\(株\)|\(有\)", "", s)
    return re.sub(r"\s+", "", s).lower()


def makers_compatible(a: str, b: str) -> bool:
    na, nb = normalize_maker(a), normalize_maker(b)
    if not na or not nb:
        return True
    return na in nb or nb in na
