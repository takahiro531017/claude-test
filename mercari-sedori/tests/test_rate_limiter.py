import random

import pytest

from sedori import db
from sedori.collector.playwright_collector import build_search_url, parse_card, robots_allows
from sedori.collector.rate_limiter import RateLimiter, RateLimitExceeded


def make(conn, max_per_hour=30):
    slept = []
    rl = RateLimiter(conn, min_interval_sec=8, jitter_sec=(2, 6), max_per_hour=max_per_hour,
                     sleep=slept.append, rng=random.Random(1))
    t = [0.0]
    rl._clock = lambda: t[0]
    return rl, slept, t


def test_interval_enforced_with_jitter():
    rl, slept, t = make(db.connect(":memory:"))
    rl.wait()
    assert slept == []
    rl.wait()
    assert 10 <= slept[0] <= 14  # 8 + jitter(2..6)


def test_elapsed_time_is_credited():
    rl, slept, t = make(db.connect(":memory:"))
    rl.wait()
    t[0] = 100
    rl.wait()
    assert slept == []


def test_hourly_cap():
    conn = db.connect(":memory:")
    rl, slept, t = make(conn, max_per_hour=2)
    rl.wait(); rl.wait()
    with pytest.raises(RateLimitExceeded):
        rl.wait()


def test_min_interval_floor():
    rl = RateLimiter(db.connect(":memory:"), min_interval_sec=1)
    assert rl.min_interval >= 5


def test_parse_card():
    it = parse_card("/item/m12345678901", "Switch 本体の画像 ¥9,800", "¥9,800", "http://i/x.jpg", "on_sale")
    assert it.item_id == "m12345678901" and it.price == 9800 and it.title == "Switch 本体"
    assert it.url.endswith("/item/m12345678901")


def test_parse_card_rejects_non_item():
    assert parse_card("/user/1", "x ¥100", "", "", "on_sale") is None
    assert parse_card("/item/m1", "no price", "", "", "on_sale") is None


def test_search_url():
    u = build_search_url("Switch", "sold_out", 500, 10000)
    assert "status=sold_out" in u and "price_max=10000" in u


class Resp:
    def __init__(self, code, text): self.status_code, self.text = code, text


class Sess:
    def __init__(self, resp): self.resp = resp
    def get(self, *a, **k): return self.resp


def test_robots():
    assert robots_allows("https://x.test/search?q=1", Sess(Resp(200, "User-agent: *\nAllow: /")))
    assert not robots_allows("https://x.test/search?q=1", Sess(Resp(200, "User-agent: *\nDisallow: /search")))
    assert not robots_allows("https://x.test/search", Sess(Resp(500, "")))
