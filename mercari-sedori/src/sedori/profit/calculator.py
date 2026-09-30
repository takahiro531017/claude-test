from __future__ import annotations

import math
import unicodedata

from ..config import ProfitConfig
from ..models import Item, MarketStat, Verdict


def size_class_for(title: str, cfg: ProfitConfig) -> str:
    t = unicodedata.normalize("NFKC", title).lower()
    for kw, cls in cfg.size_class_by_keyword.items():
        if kw.lower() in t:
            return cls
    return cfg.default_size_class


def shipping_cost(title: str, cfg: ProfitConfig, size_class: str = "") -> int:
    cls = size_class or size_class_for(title, cfg)
    if cls in cfg.shipping_table:
        return int(cfg.shipping_table[cls])
    return int(max(cfg.shipping_table.values()))  # 未定義区分は安全側


def calc_profit(item: Item, market: MarketStat | None, cfg: ProfitConfig) -> Verdict:
    if market is None:
        return Verdict(ok=False, reason="相場データなし")
    sale = market.median
    fee = math.floor(sale * cfg.fee_rate)
    ship = shipping_cost(item.title, cfg, item.size_class)
    inbound = ship if item.shipping_payer == "buyer" else 0  # 着払いは仕入れ時に送料を負担
    net = sale - item.price - fee - ship - cfg.packing_cost - inbound
    base = sale if cfg.margin_basis == "sale" else item.price
    rate = net / base if base else 0.0
    v = Verdict(
        ok=False, sale_price=sale, fee=fee, shipping=ship, packing=cfg.packing_cost,
        inbound_shipping=inbound, net_profit=net, margin_rate=rate,
    )
    if cfg.require_reliable_market and not market.reliable:
        v.reason = f"相場の信頼度低(件数{market.count})"
    elif net < cfg.min_net_profit:
        v.reason = f"実利益不足({net}円)"
    elif rate < cfg.min_margin_rate:
        v.reason = f"利益率不足({rate:.1%})"
    else:
        v.ok = True
    return v
