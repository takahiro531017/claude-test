import pytest

from sedori.pricing.normalizer import normalize_title, parse_title


def test_same_product_different_wording():
    a = normalize_title("iPhone 12 128GB ブラック 美品")
    b = normalize_title("【送料無料】Apple iPhone12 128gb 黒 SIMフリー")
    assert a == b


def test_capacity_distinguishes():
    assert normalize_title("iPhone12 64GB 黒") != normalize_title("iPhone12 128GB 黒")


def test_color_distinguishes():
    assert normalize_title("iPhone12 128GB 黒") != normalize_title("iPhone12 128GB 白")


def test_model_number_extracted():
    p = parse_title("Nintendo Switch HAC-001 ネオンブルー 本体")
    assert p["models"] == ["hac001"]  # ハイフン有無を吸収
    assert p["color"] == "blue"


def test_fullwidth_and_case():
    assert normalize_title("ＷＨ－１０００ＸＭ４ ブラック") == normalize_title("wh-1000xm4 black")


def test_no_model_falls_back_to_words():
    assert normalize_title("AirPods Pro 美品").startswith("airpods")


def test_units_not_model():
    assert "5g" not in parse_title("スマホ 5G 対応")["models"]


def test_capacity_tb():
    assert parse_title("SSD 1TB")["capacity"] == "1tb"


def test_hyphen_variants_match():
    assert normalize_title("HAC-001 ブルー") == normalize_title("HAC001 ブルー")
