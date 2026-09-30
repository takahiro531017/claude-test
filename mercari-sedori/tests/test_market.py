from datetime import datetime

from sedori import db
from sedori.config import MarketConfig
from sedori.pricing.market import compute_market, market_for_key

CFG = MarketConfig()


def test_median_and_trim():
    prices = [1] + [1000] * 8 + [99999]  # 上下10%(各1件)除外
    m = compute_market(prices, CFG)
    assert m.median == 1000 and m.count == 10 and m.reliable


def test_low_confidence():
    m = compute_market([1000, 1100, 1200], CFG)
    assert m.count == 3 and not m.reliable


def test_empty():
    assert compute_market([], CFG) is None


def test_window_filters_old_sales():
    conn = db.connect(":memory:")
    now = datetime(2026, 6, 30)
    rows = [("a", 1000, "2026-06-20"), ("b", 2000, "2026-06-25"), ("c", 9000, "2026-04-01")]
    for i, p, d in rows:
        conn.execute("INSERT INTO sold_items(item_id,title,price,sold_at,product_key) VALUES(?,?,?,?,?)",
                     (i, "t", p, d, "k"))
    m = market_for_key(conn, "k", CFG, now)
    assert m.count == 2 and m.median == 1500
