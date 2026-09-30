from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Item:
    item_id: str
    title: str
    price: int
    condition: str = ""
    shipping_payer: str = "seller"  # seller=出品者負担(送料込み) / buyer=購入者負担(着払い)
    listed_at: str = ""
    url: str = ""
    image_url: str = ""
    status: str = "on_sale"  # on_sale / sold
    sold_at: str = ""
    category: str = ""
    description: str = ""
    product_key: str = ""


@dataclass
class MarketStat:
    median: int
    count: int
    reliable: bool


@dataclass
class Verdict:
    ok: bool
    reason: str = ""
    sale_price: int = 0
    fee: int = 0
    shipping: int = 0
    packing: int = 0
    inbound_shipping: int = 0
    net_profit: int = 0
    margin_rate: float = 0.0
