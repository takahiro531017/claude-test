from __future__ import annotations

import logging

import requests

from ..models import Item, MarketStat, Verdict

log = logging.getLogger(__name__)


class ConsoleNotifier:
    """Webhook未設定・dry-run用。標準出力に表示する。"""

    name = "console"

    def send(self, item: Item, market: MarketStat, verdict: Verdict) -> bool:
        print(
            f"[候補] {item.title} 仕入{item.price}円 想定売価{verdict.sale_price}円 "
            f"実利益{verdict.net_profit}円 利益率{verdict.margin_rate:.1%} 相場{market.count}件 {item.url}"
        )
        return True


class DiscordNotifier:
    name = "discord"

    def __init__(self, webhook_url: str, session: requests.Session | None = None):
        self._url = webhook_url  # ログ・例外メッセージには出さない
        self._http = session or requests.Session()

    def build_payload(self, item: Item, market: MarketStat, verdict: Verdict) -> dict:
        embed = {
            "title": item.title[:250],
            "url": item.url or None,
            "fields": [
                {"name": "仕入れ価格", "value": f"{item.price:,}円", "inline": True},
                {"name": "想定売価", "value": f"{verdict.sale_price:,}円", "inline": True},
                {"name": "実利益", "value": f"{verdict.net_profit:,}円", "inline": True},
                {"name": "利益率", "value": f"{verdict.margin_rate:.1%}", "inline": True},
                {"name": "相場件数", "value": f"{market.count}件", "inline": True},
                {"name": "商品URL", "value": item.url or "-", "inline": False},
            ],
        }
        if item.image_url:
            embed["image"] = {"url": item.image_url}
        return {"embeds": [embed]}

    def send(self, item: Item, market: MarketStat, verdict: Verdict) -> bool:
        try:
            r = self._http.post(self._url, json=self.build_payload(item, market, verdict), timeout=15)
            r.raise_for_status()
            return True
        except requests.RequestException as e:
            log.error("Discord通知に失敗: %s", type(e).__name__)
            return False
