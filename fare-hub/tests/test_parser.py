import pytest

from app.parser import ParseError, parse_date, parse_pdf
from tools.make_dummy_pdfs import NOTES, Spec, build_pdf, default_specs, make_rates


@pytest.mark.parametrize("spec", default_specs(), ids=lambda s: s.origin)
def test_rates_match_ground_truth(st, spec):
    res = parse_pdf(build_pdf(spec), st)
    truth = {k: v for k, v in make_rates(spec).items() if k not in spec.missing + spec.dashed}
    assert res.rates == truth  # 全件一致（欠損セルは欠損のまま、他セルの取り違え無し）


def test_layouts_use_different_profiles(st):
    a, b, _ = default_specs()
    assert parse_pdf(build_pdf(a), st).profile == "standard"
    assert parse_pdf(build_pdf(b), st).profile == "branch_alt"


def test_header_fields(st):
    res = parse_pdf(build_pdf(Spec("拠点A", valid_from="2025年4月1日", valid_to="2026年3月31日")), st)
    assert res.header["origin"] == "拠点A"
    assert (res.header["valid_from"], res.header["valid_to"]) == ("2025-04-01", "2026-03-31")
    assert res.header["quote_no"] == "Q-2025-001" and res.header["customer_code"] == "C-0001"
    assert res.header["closing_day"] == "月末"


def test_alt_layout_aliases_and_header(st):
    res = parse_pdf(build_pdf(default_specs()[1]), st)  # 別ラベル・別名地帯・逆順
    assert res.header["origin"] == "拠点B" and res.header["closing_day"] == "20日"
    assert len(res.rates) == 132


def test_weights_and_notes(st):
    res = parse_pdf(build_pdf(Spec("拠点A")), st)
    assert res.weights == {60: 2, 80: 5, 100: 10, 140: 20, 160: 30, 170: 50}
    assert [c for c, _ in res.notes] == ["okinawa", "island", "insurance", "volume", "limit"]
    assert [t for _, t in res.notes] == NOTES  # ページ番号「1 / 1」は除外される


def test_missing_cells_are_detected_not_guessed(st):
    sp = Spec("拠点C", missing=[("関東", 100)], dashed=[("四国", 60)])
    res = parse_pdf(build_pdf(sp), st)
    assert ("関東", 100) not in res.rates and ("四国", 60) not in res.rates
    assert len(res.rates) == 130


@pytest.mark.parametrize("text,iso", [("2025年4月1日", "2025-04-01"), ("2025/04/01", "2025-04-01"),
                                      ("令和7年4月1日", "2025-04-01"), ("2025-4-1", "2025-04-01"), ("2025年13月1日", None), ("なし", None)])
def test_parse_date(text, iso):
    assert parse_date(text) == iso


def test_garbage_is_rejected_with_kind_only(st):
    for data, kind in [(b"hello", "not_a_pdf"), (b"%PDF-1.4 broken", None)]:
        with pytest.raises(ParseError) as e:
            parse_pdf(data, st)
        if kind:
            assert e.value.kind == kind
        assert "broken" not in e.value.kind


def test_transposed_layout_with_letter_spaced_text(st):
    """行=サイズ・列=地帯／字間をあけた地帯名・日付／発地ラベル無し。"""
    sp = Spec("拠点D", layout="transposed", seed=4)
    res = parse_pdf(build_pdf(sp), st)
    assert res.profile == "transposed"
    assert res.rates == make_rates(sp)
    assert (res.header["valid_from"], res.header["valid_to"]) == ("2025-04-01", "2026-03-31")
    assert res.weights == {60: 2, 80: 5, 100: 10, 140: 20, 160: 30, 170: 50}
    assert [c for c, _ in res.notes] == ["okinawa", "island", "insurance", "volume", "limit"]
    assert {"kind": "header_missing", "detail": "origin"} in res.warnings


def test_transposed_missing_cell_detected(st):
    sp = Spec("拠点D", layout="transposed", seed=4, missing=[("関東", 100)])
    assert ("関東", 100) not in parse_pdf(build_pdf(sp), st).rates


def test_four_digit_prices_without_comma():
    from app.parser import PRICE_RE
    assert PRICE_RE.match("1234") and PRICE_RE.match("1,234") and PRICE_RE.match("¥1,234円") and not PRICE_RE.match("12kg")
