from __future__ import annotations

import random
import sqlite3
import time
from typing import Callable


class RateLimitExceeded(RuntimeError):
    pass


class RateLimiter:
    """リクエスト間隔(最低 min_interval + ランダム待機)と1時間あたり上限を強制する。
    履歴は request_log テーブルに保存するため、プロセスを跨いで上限が効く。"""

    def __init__(
        self,
        conn: sqlite3.Connection,
        min_interval_sec: float = 8,
        jitter_sec: tuple[float, float] = (2, 6),
        max_per_hour: int = 30,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
    ):
        self.conn = conn
        self.min_interval = max(float(min_interval_sec), 5.0)  # 下限5秒を強制
        self.jitter = jitter_sec
        self.max_per_hour = max_per_hour
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._last: float | None = None
        self._clock = time.monotonic

    def used_last_hour(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM request_log WHERE ts >= datetime('now','-1 hour')"
        ).fetchone()[0]

    def wait(self, kind: str = "search") -> None:
        if self.used_last_hour() >= self.max_per_hour:
            raise RateLimitExceeded(f"1時間あたりの上限({self.max_per_hour}回)に達しました")
        if self._last is not None:
            elapsed = self._clock() - self._last
            need = self.min_interval + self._rng.uniform(*self.jitter) - elapsed
            if need > 0:
                self._sleep(need)
        self._last = self._clock()
        self.conn.execute("INSERT INTO request_log(kind) VALUES(?)", (kind,))
        self.conn.commit()
