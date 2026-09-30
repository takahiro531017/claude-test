from __future__ import annotations

import logging
import time
from datetime import datetime, time as dtime
from typing import Callable

import schedule

log = logging.getLogger(__name__)


def _t(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def in_quiet_hours(now: datetime, start: str | None, end: str | None) -> bool:
    """start<=now<end。日跨ぎ(22:00-07:00)にも対応。start==end は停止なし。"""
    if not start or not end:
        return False
    s, e, n = _t(start), _t(end), now.time()
    if s == e:
        return False
    return s <= n < e if s < e else (n >= s or n < e)


def run_forever(job: Callable[[], None], interval_minutes: int, quiet: dict | None = None) -> None:
    quiet = quiet or {}

    def guarded() -> None:
        if in_quiet_hours(datetime.now(), quiet.get("start"), quiet.get("end")):
            log.info("夜間停止時間のためスキップ")
            return
        try:
            job()
        except Exception:
            log.exception("定期実行中にエラー")

    schedule.every(interval_minutes).minutes.do(guarded)
    guarded()
    while True:
        schedule.run_pending()
        time.sleep(30)
