from types import SimpleNamespace

from sedori.listing.generator import check_text, generate_listing, markdown_plan, recommend_price
from sedori.scheduler import in_quiet_hours
from datetime import datetime


class FakeClient:
    def __init__(self, text):
        self.messages = SimpleNamespace(create=lambda **kw: SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)]))


def test_markdown_plan_respects_floor():
    plan = markdown_plan(10000, [{"after_days": 3, "rate": -0.03}, {"after_days": 7, "rate": -0.5}], floor_price=8000)
    assert plan == [{"after_days": 0, "price": 10000}, {"after_days": 3, "price": 9700},
                    {"after_days": 7, "price": 8000}]


def test_recommend_price_never_below_floor():
    price, floor = recommend_price(5000, purchase_price=4500, shipping=850, packing=100, min_profit=500)
    assert price == floor and floor > 5950


def test_generate_listing_parses_json_and_flags_banned():
    fake = FakeClient('```json\n{"title":"Switch HAC-001 青","description":"激安です。傷あり。"}\n```')
    d = generate_listing(fake, "m", {"title": "x"}, 15000, 9000, [{"after_days": 3, "rate": -0.03}])
    assert d.title.startswith("Switch") and d.recommended_price >= 15000
    assert any("激安" in w for w in d.warnings)
    assert d.markdown_plan[1]["after_days"] == 3


def test_check_text_long_title():
    assert check_text("あ" * 41, "ok")


def test_quiet_hours():
    f = lambda h, m=0: in_quiet_hours(datetime(2026, 1, 1, h, m), "00:00", "07:00")
    assert f(3) and not f(7) and not f(12)
    g = lambda h: in_quiet_hours(datetime(2026, 1, 1, h), "22:00", "06:00")
    assert g(23) and g(5) and not g(12)
    assert not in_quiet_hours(datetime.now(), None, None)
