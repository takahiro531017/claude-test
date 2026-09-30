"""出品支援: Claude API でタイトル・説明文を生成し、価格と値下げ戦略は相場から算出する。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

SYSTEM = (
    "あなたはフリマアプリの出品文を作る assistant です。次を厳守してください。\n"
    "- 状態は与えられた事実のみを書く。傷・汚れ・動作未確認などマイナス情報も隠さず書く。\n"
    "- 「激安」「最安」「絶対」「完璧」「保証」「新品同様」など誇大・断定表現は使わない。\n"
    "- 与えられていない付属品・購入時期・使用歴を創作しない。\n"
    "- タイトルは40文字以内。型番・容量・色を含める。\n"
    '- 出力は JSON のみ: {"title": "...", "description": "..."}'
)
BANNED = ["激安", "最安", "絶対", "完璧", "保証", "新品同様", "神", "格安", "業界最安", "確実"]


@dataclass
class ListingDraft:
    title: str
    description: str
    recommended_price: int
    markdown_plan: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def round_price(p: float, unit: int = 10) -> int:
    return int(round(p / unit) * unit)


def markdown_plan(base_price: int, strategy: list[dict], floor_price: int = 0) -> list[dict]:
    """strategy: [{after_days, rate(負の値, 元価格に対する累積率)}]。floor_price を下回らない。"""
    plan = [{"after_days": 0, "price": base_price}]
    for s in sorted(strategy, key=lambda x: x["after_days"]):
        price = max(round_price(base_price * (1 + s["rate"])), floor_price)
        plan.append({"after_days": s["after_days"], "price": price})
    return plan


def recommend_price(median: int | None, purchase_price: int, fee_rate: float = 0.10,
                    shipping: int = 0, packing: int = 0, min_profit: int = 0) -> tuple[int, int]:
    """(推奨価格, 値下げ下限)。下限=この価格未満だと min_profit を割る売価。"""
    fixed = purchase_price + shipping + packing + min_profit
    floor = round_price(fixed / (1 - fee_rate)) + 10
    base = round_price(median) if median else floor
    return max(base, floor), floor


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("Claudeの応答からJSONを取得できませんでした")
    return json.loads(m.group(0))


def check_text(title: str, description: str) -> list[str]:
    w = [f"誇大表現の疑い: {b}" for b in BANNED if b in title or b in description]
    if len(title) > 40:
        w.append(f"タイトルが40文字超({len(title)})")
    return w


def generate_listing(client, model: str, facts: dict, median: int | None, purchase_price: int,
                     strategy: list[dict], fee_rate: float = 0.10, shipping: int = 0,
                     packing: int = 100, min_profit: int = 0) -> ListingDraft:
    """client は anthropic.Anthropic 互換(messages.create を持つ)。"""
    resp = client.messages.create(
        model=model, max_tokens=1000, system=SYSTEM,
        messages=[{"role": "user", "content": "商品情報(事実):\n" + json.dumps(facts, ensure_ascii=False)}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    data = _extract_json(text)
    title, desc = data["title"].strip(), data["description"].strip()
    price, floor = recommend_price(median, purchase_price, fee_rate, shipping, packing, min_profit)
    return ListingDraft(title, desc, price, markdown_plan(price, strategy, floor), check_text(title, desc))
