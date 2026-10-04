from datetime import date

import pytest

from shiire_check.normalize import (
    Normalizer, makers_compatible, parse_amount, parse_date,
)


@pytest.fixture
def n():
    return Normalizer()


@pytest.mark.parametrize("a,b", [
    ("ＡＢＣ１２３", "abc123"),            # 全角半角・大文字小文字
    ("2026-10-0001", "2026100001"),        # ハイフン有無
    ("2026‐10−0001", "2026-10-0001"),      # 各種ハイフン
    ("004567", "4567"),                    # 先頭ゼロ
    ("００４５６７", "4567"),              # 全角＋先頭ゼロ
    ("TK-00123", "TK-123"),                # 英字接頭辞の後のゼロ
    (" 12 34　", "1234"),              # 半角・全角スペース
    ("DE_7001", "DE7001"),
])
def test_equivalent(n, a, b):
    assert n(a) == n(b) != ""


@pytest.mark.parametrize("a,b", [
    ("4567", "4568"),
    ("A-123", "B-123"),
    ("1230", "123"),                       # 末尾のゼロは消さない
    ("0", "00"),                           # 0 だけは空にならず、00 → 0 に揃う
])
def test_different_or_edge(n, a, b):
    if (a, b) == ("0", "00"):
        assert n(a) == n(b) == "0"
    else:
        assert n(a) != n(b)


def test_empty(n):
    assert n(None) == "" and n("  - ") == ""


def test_rules_are_configurable():
    n = Normalizer({"strip_leading_zeros": False, "remove_chars": [], "uppercase": False})
    assert n("004567") != n("4567")
    assert n("A-1") != n("A1")
    assert n("a1") != n("A1")


def test_strip_prefix():
    n = Normalizer({"strip_prefixes": ["No.", "№"]})
    assert n("No. 1234") == n("1234")
    assert n("№1234") == n("1234")


def test_parse_amount():
    assert parse_amount("¥12,345") == 12345
    assert parse_amount("１２，３４５円") == 12345
    assert parse_amount(None) is None and parse_amount("abc") is None
    assert parse_amount(10) == 10


def test_parse_date():
    assert parse_date("2026-10-05") == date(2026, 10, 5)
    assert parse_date("2026年10月5日") == date(2026, 10, 5)
    assert parse_date("令和8年10月5日") == date(2026, 10, 5)
    assert parse_date("2026/10/5") == date(2026, 10, 5)
    assert parse_date("20261005") == date(2026, 10, 5)
    assert parse_date("2026-13-40") is None and parse_date("") is None


def test_makers():
    assert makers_compatible("東海部品株式会社", "東海部品")
    assert makers_compatible("(株)北斗化学", "北斗化学")
    assert not makers_compatible("山田製作所", "東海部品")
    assert makers_compatible("", "東海部品")   # 片方不明なら比較しない
