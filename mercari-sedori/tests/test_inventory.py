import pytest

from sedori import db
from sedori.inventory import store


def test_flow_and_report(tmp_path):
    c = db.connect(":memory:")
    a = store.add_purchase(c, "Switch", 9000, purchased_at="2026-06-01")
    store.mark_listed(c, a, 15000, "2026-06-02")
    store.mark_sold(c, a, 15000, "2026-06-11", shipping_cost=850, packing_cost=100)
    b = store.add_purchase(c, "AirPods", 6000, purchased_at="2026-06-05")
    store.mark_sold(c, b, 12000, "2026-06-25", shipping_cost=450, packing_cost=100)
    rep = store.monthly_report(c)
    assert len(rep) == 1
    r = rep[0]
    # a: 15000-9000-1500-850-100=3550 / b: 12000-6000-1200-450-100=4250
    assert r["profit"] == 7800 and r["revenue"] == 27000 and r["count"] == 2
    assert r["avg_turnover_days"] == 15.0  # (10+20)/2
    n = store.export_csv(c, tmp_path / "x.csv", 2026)
    assert n == 2 and "3550" in (tmp_path / "x.csv").read_text(encoding="utf-8-sig")


def test_stagnant():
    c = db.connect(":memory:")
    store.add_purchase(c, "old", 1000, purchased_at="2026-01-01")
    store.add_purchase(c, "new", 1000, purchased_at="2026-06-20")
    s = store.stagnant_stock(c, 30, today="2026-06-30")
    assert [x["title"] for x in s] == ["old"]


def test_invalid_transition():
    c = db.connect(":memory:")
    a = store.add_purchase(c, "x", 1000)
    store.mark_sold(c, a, 2000)
    with pytest.raises(ValueError):
        store.mark_listed(c, a, 2000)
    with pytest.raises(ValueError):
        store.mark_sold(c, 999, 1)
