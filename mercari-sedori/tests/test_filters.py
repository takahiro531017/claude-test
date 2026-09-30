import pytest

from sedori.config import ExcludeConfig
from sedori.models import Item
from sedori.profit.filters import check_exclusion

CFG = ExcludeConfig(
    keywords_junk=("ジャンク", "動作未確認"),
    keywords_fake=("コピー", "レプリカ"),
    brands=("ルイヴィトン", "gucci"),
    categories=("チケット", "食品", "化粧品"),
    ng_words=("ロット売り",),
)


def it(title, category="", desc=""):
    return Item(item_id="1", title=title, price=1000, category=category, description=desc)


@pytest.mark.parametrize(
    "title,label",
    [
        ("Switch ジャンク品", "ジャンク"),
        ("ゲーム機 動作未確認", "ジャンク"),
        ("ヴィトン風 レプリカ バッグ", "偽物"),
        ("GUCCI 財布", "ブランド"),
        ("ｇｕｃｃｉ 財布", "ブランド"),
        ("ライブ チケット 2枚", "転売禁止"),
        ("ロット売り 10個", "NGワード"),
    ],
)
def test_excluded(title, label):
    r = check_exclusion(it(title), CFG)
    assert r and label in r


def test_category_field():
    assert "転売禁止" in check_exclusion(it("お菓子", category="食品"), CFG)


def test_description_checked():
    assert check_exclusion(it("Switch 本体", desc="画面にジャンク部品あり"), CFG)


def test_clean_item_passes():
    assert check_exclusion(it("Nintendo Switch 本体 美品"), CFG) is None
