"""設定の読み込み（config/*.yaml）。実行時にネットワークは使わない。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(os.environ.get("FARE_HUB_CONFIG_DIR", ROOT / "config"))


@dataclass
class Region:
    name: str
    aliases: list[str]
    prefectures: list[str]


@dataclass
class Settings:
    sizes: list[int]
    weight_sizes: dict[int, int]
    regions: list[Region]
    special_prefectures: list[str]
    parser: dict
    region_names: list[str] = field(init=False)

    def __post_init__(self) -> None:
        self.region_names = [r.name for r in self.regions]

    # 地帯名・別名 -> 正式な地帯名
    def region_lookup(self) -> dict[str, str]:
        m: dict[str, str] = {}
        for r in self.regions:
            m[r.name] = r.name
            for a in r.aliases:
                m[a] = r.name
        return m

    def resolve_destination(self, text: str) -> dict:
        """地帯名または都道府県名(「東京」「東京都」可)から地帯を引く。"""
        t = "".join(text.split())
        out = {"query": text, "region": None, "prefecture": None, "special": False}
        if not t:
            return out
        lk = self.region_lookup()
        if t in lk:
            out["region"] = lk[t]
            return out
        for sp in self.special_prefectures:
            if t in _pref_forms(sp):
                out.update(prefecture=sp, special=True)
                return out
        for r in self.regions:
            for p in r.prefectures:
                if t in _pref_forms(p):
                    out.update(region=r.name, prefecture=p)
                    return out
        return out


def _pref_forms(pref: str) -> set[str]:
    """都道府県の表記ゆれ（「東京都」「東京」）。北海道は接尾辞を落とさない。"""
    forms = {pref}
    if pref != "北海道" and pref[-1] in "都府県":
        forms.add(pref[:-1])
    return forms


def _load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_settings() -> Settings:
    reg = _load_yaml("regions.yaml")
    return Settings(
        sizes=[int(s) for s in reg["sizes"]],
        weight_sizes={int(k): int(v) for k, v in reg["weight_sizes"].items()},
        regions=[Region(r["name"], r.get("aliases") or [], r.get("prefectures") or []) for r in reg["regions"]],
        special_prefectures=reg.get("special_prefectures") or [],
        parser=_load_yaml("parser.yaml"),
    )
