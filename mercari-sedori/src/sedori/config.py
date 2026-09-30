from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULTS: dict = {
    "search": {"keywords": [], "price_min": 0, "price_max": 10000, "conditions": []},
    "rate_limit": {"min_interval_sec": 8, "jitter_sec": [2, 6], "max_searches_per_hour": 30},
    "market": {"window_days": 30, "trim_ratio": 0.10, "min_samples": 5},
    "profit": {
        "fee_rate": 0.10,
        "packing_cost": 100,
        "min_net_profit": 1000,
        "min_margin_rate": 0.15,
        "margin_basis": "sale",
        "require_reliable_market": True,
        "shipping_table": {"compact": 450, "s60": 750, "s80": 850, "s100": 1050},
        "default_size_class": "s100",
        "size_class_by_keyword": {},
    },
    "exclude": {
        "keywords_junk": [],
        "keywords_fake": [],
        "brands": [],
        "categories": [],
        "ng_words": [],
    },
    "notify": {"discord": {"enabled": True}},
    "schedule": {"interval_minutes": 45, "quiet_hours": {"start": "00:00", "end": "07:00"}},
    "listing": {"model": "claude-sonnet-5-5", "markdown_strategy": []},
    "db_path": "data/sedori.db",
    "log_dir": "logs",
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


@dataclass(frozen=True)
class MarketConfig:
    window_days: int = 30
    trim_ratio: float = 0.10
    min_samples: int = 5


@dataclass(frozen=True)
class ProfitConfig:
    fee_rate: float = 0.10
    packing_cost: int = 100
    min_net_profit: int = 1000
    min_margin_rate: float = 0.15
    margin_basis: str = "sale"
    require_reliable_market: bool = True
    shipping_table: dict = field(default_factory=lambda: {"s100": 1050})
    default_size_class: str = "s100"
    size_class_by_keyword: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ExcludeConfig:
    keywords_junk: tuple = ()
    keywords_fake: tuple = ()
    brands: tuple = ()
    categories: tuple = ()
    ng_words: tuple = ()


@dataclass(frozen=True)
class Config:
    raw: dict
    market: MarketConfig
    profit: ProfitConfig
    exclude: ExcludeConfig
    price_min: int
    price_max: int
    db_path: str
    log_dir: str


def build_config(data: dict | None = None) -> Config:
    raw = _merge(DEFAULTS, data or {})
    ex = raw["exclude"]
    return Config(
        raw=raw,
        market=MarketConfig(**raw["market"]),
        profit=ProfitConfig(**raw["profit"]),
        exclude=ExcludeConfig(**{k: tuple(v) for k, v in ex.items()}),
        price_min=int(raw["search"]["price_min"]),
        price_max=int(raw["search"]["price_max"]),
        db_path=raw["db_path"],
        log_dir=raw["log_dir"],
    )


def load_config(path: str | Path = "config.yaml") -> Config:
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    return build_config(data)
