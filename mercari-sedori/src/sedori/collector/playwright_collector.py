"""Playwright による公開検索ページの収集(ログインなし・閲覧のみ)。

注意:
- 自動ログイン・自動購入・自動コメントは実装しない。
- 起動時に robots.txt を確認し、禁止されているパスは取得しない。
- 全ページ遷移の前に RateLimiter.wait() を必ず通す。
- セレクタはメルカリ側のDOM変更で壊れ得る。取得0件のときは警告ログを出す。
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Iterable
from urllib import robotparser
from urllib.parse import urlencode, urlparse

import requests

from ..models import Item
from .rate_limiter import RateLimiter

log = logging.getLogger(__name__)

BASE = "https://jp.mercari.com"
SEARCH_PATH = "/search"
UA = "sedori-personal-tool/0.1 (personal use; low-rate)"
_ID_RE = re.compile(r"/item/(m\d+)")
_PRICE_RE = re.compile(r"[¥￥]\s*([\d,]+)|([\d,]+)\s*円")


def build_search_url(keyword: str, status: str, price_min: int, price_max: int) -> str:
    q = {"keyword": keyword, "status": status, "price_min": price_min, "price_max": price_max,
         "sort": "created_time", "order": "desc"}
    return f"{BASE}{SEARCH_PATH}?{urlencode(q)}"


def robots_allows(url: str, session: requests.Session | None = None) -> bool:
    """robots.txt を取得して url が許可されているか判定。取得できない場合は安全側で False。"""
    p = urlparse(url)
    try:
        r = (session or requests).get(f"{p.scheme}://{p.netloc}/robots.txt", timeout=15,
                                      headers={"User-Agent": UA})
        if r.status_code != 200:
            return False
        rp = robotparser.RobotFileParser()
        rp.parse(r.text.splitlines())
        return rp.can_fetch(UA, url)
    except requests.RequestException:
        return False


def parse_card(href: str, label: str, text: str, image_url: str, status: str) -> Item | None:
    """検索結果カード1件(anchorのhref・alt/aria-label・表示テキスト)を Item に変換する。"""
    m = _ID_RE.search(href or "")
    if not m:
        return None
    blob = f"{label} {text}"
    pm = _PRICE_RE.search(blob)
    if not pm:
        return None
    price = int((pm.group(1) or pm.group(2)).replace(",", ""))
    title = re.sub(r"の(画像|写真).*$", "", (label or "").strip()) or text.strip().split("\n")[0]
    title = _PRICE_RE.sub("", title).strip()
    item_id = m.group(1)
    return Item(
        item_id=item_id, title=title, price=price, url=f"{BASE}/item/{item_id}",
        image_url=image_url or "", status=status,
        # 検索結果には出品日時・売却日時が出ないため取得日で代用
        listed_at=datetime.now().strftime("%Y-%m-%d") if status == "on_sale" else "",
        sold_at=datetime.now().strftime("%Y-%m-%d") if status == "sold" else "",
    )


class PlaywrightCollector:
    def __init__(self, keywords: list[str], price_min: int, price_max: int, limiter: RateLimiter,
                 headless: bool = True, max_items_per_search: int = 50):
        self.keywords, self.price_min, self.price_max = keywords, price_min, price_max
        self.limiter, self.headless, self.max_items = limiter, headless, max_items_per_search

    def _scrape(self, status_param: str, status: str) -> list[Item]:
        from playwright.sync_api import sync_playwright  # 遅延import(未導入でもCSV版は動く)

        items: dict[str, Item] = {}
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless)
            ctx = browser.new_context(user_agent=UA, locale="ja-JP")
            page = ctx.new_page()
            try:
                for kw in self.keywords:
                    url = build_search_url(kw, status_param, self.price_min, self.price_max)
                    if not robots_allows(url):
                        log.warning("robots.txt により取得不可のためスキップ: keyword=%s", kw)
                        continue
                    self.limiter.wait("search")
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    try:
                        page.wait_for_selector('a[href*="/item/m"]', timeout=15000)
                    except Exception:
                        log.warning("検索結果を検出できません(DOM変更/該当なし): keyword=%s", kw)
                        continue
                    cards = page.eval_on_selector_all(
                        'a[href*="/item/m"]',
                        """els => els.map(a => ({href: a.getAttribute('href'),
                            label: (a.querySelector('img')||{}).alt || a.getAttribute('aria-label') || '',
                            text: a.innerText || '',
                            img: (a.querySelector('img')||{}).src || ''}))""",
                    )
                    n0 = len(items)
                    for c in cards[: self.max_items]:
                        it = parse_card(c["href"], c["label"], c["text"], c["img"], status)
                        if it:
                            items.setdefault(it.item_id, it)
                    log.info("keyword=%s status=%s 取得=%d", kw, status, len(items) - n0)
            finally:
                browser.close()
        return list(items.values())

    def fetch_active(self) -> Iterable[Item]:
        return self._scrape("on_sale", "on_sale")

    def fetch_sold(self) -> Iterable[Item]:
        return self._scrape("sold_out", "sold")
