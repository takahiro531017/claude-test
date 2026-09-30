from sedori.config import ProfitConfig
from sedori.models import Item, MarketStat
from sedori.profit.calculator import calc_profit, shipping_cost

CFG = ProfitConfig(
    shipping_table={"compact": 450, "s80": 850, "s100": 1050},
    default_size_class="s100",
    size_class_by_keyword={"switch": "s80", "airpods": "compact"},
)
REL = MarketStat(median=10000, count=10, reliable=True)


def item(price=5000, title="Nintendo Switch", payer="seller"):
    return Item(item_id="1", title=title, price=price, shipping_payer=payer)


def test_profit_formula():
    v = calc_profit(item(5000), REL, CFG)
    # 10000 - 5000 - 1000(fee) - 850 - 100 = 3050
    assert v.net_profit == 3050
    assert v.fee == 1000
    assert v.margin_rate == 3050 / 10000
    assert v.ok


def test_buyer_pays_inbound_shipping():
    v = calc_profit(item(5000, payer="buyer"), REL, CFG)
    assert v.net_profit == 3050 - 850


def test_default_size_class_is_safe_side():
    assert shipping_cost("謎の商品", CFG) == 1050
    assert shipping_cost("AirPods Pro", CFG) == 450


def test_unknown_size_class_uses_max():
    cfg = ProfitConfig(shipping_table={"a": 300, "b": 900}, default_size_class="zzz")
    assert shipping_cost("x", cfg) == 900


def test_min_profit_boundary():
    # net == 1000 exactly (min_net_profit 以上) -> pass
    cfg = ProfitConfig(shipping_table={"s80": 850}, default_size_class="s80", min_margin_rate=0.10)
    v = calc_profit(item(price=10000 - 1000 - 850 - 100 - 1000), REL, cfg)
    assert v.net_profit == 1000 and v.ok


def test_below_min_profit():
    v = calc_profit(item(price=7100), REL, CFG)  # net 950
    assert not v.ok and "実利益不足" in v.reason


def test_margin_rate_too_low():
    cfg = ProfitConfig(shipping_table={"s80": 850}, default_size_class="s80", min_net_profit=1000, min_margin_rate=0.15)
    m = MarketStat(median=30000, count=10, reliable=True)
    v = calc_profit(item(price=24000), m, cfg)  # net=30000-24000-3000-850-100=2050 -> 6.8%
    assert v.net_profit >= 1000 and not v.ok and "利益率" in v.reason


def test_margin_basis_cost():
    cfg = ProfitConfig(shipping_table={"s80": 850}, default_size_class="s80", margin_basis="cost")
    v = calc_profit(item(5000), REL, cfg)
    assert v.margin_rate == 3050 / 5000


def test_unreliable_market_rejected():
    v = calc_profit(item(1000), MarketStat(median=10000, count=3, reliable=False), CFG)
    assert not v.ok and "信頼度低" in v.reason


def test_unreliable_allowed_when_configured():
    cfg = ProfitConfig(shipping_table={"s80": 850}, default_size_class="s80", require_reliable_market=False)
    assert calc_profit(item(1000), MarketStat(10000, 3, False), cfg).ok


def test_no_market():
    assert not calc_profit(item(), None, CFG).ok


def test_fee_floor():
    m = MarketStat(median=1999, count=9, reliable=True)
    assert calc_profit(item(100), m, CFG).fee == 199
