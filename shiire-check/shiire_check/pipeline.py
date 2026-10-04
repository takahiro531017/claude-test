"""伝票の一括読み取り（並列・キャッシュ・失敗の隔離）。"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from shiire_check.cache import Cache
from shiire_check.imaging import PageRef, prepare_for_api
from shiire_check.schema import ReadResult

log = logging.getLogger(__name__)


class Cancelled(Exception):
    pass


@dataclass
class SlipReading:
    ref: PageRef
    result: ReadResult | None = None
    error: str | None = None
    from_cache: bool = False

    @property
    def key(self) -> str:
        return self.ref.key


def read_all(
    pages: list[PageRef],
    reader,
    cache: Cache | None,
    cfg: dict,
    progress: Callable[[int, int], None] | None = None,
    cancel: threading.Event | None = None,
) -> list[SlipReading]:
    """全ページを読み取る。1枚の失敗（例外）は error に記録して続行し、全体は止めない。"""
    total = len(pages)
    out: list[SlipReading | None] = [None] * total
    done = 0
    lock = threading.Lock()
    img_cfg = cfg["image"]

    def work(i: int) -> None:
        nonlocal done
        ref = pages[i]
        sr = SlipReading(ref)
        try:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            if ref.error:
                sr.error = ref.error
            else:
                cached = cache.get_reading(ref.key, reader.id) if cache and reader.cacheable else None
                if cached is not None:
                    sr.result, sr.from_cache = cached, True
                else:
                    sr.result = reader.read(
                        ref,
                        lambda: prepare_for_api(
                            ref, img_cfg["max_long_edge"], img_cfg["jpeg_quality"], img_cfg["pdf_dpi"]
                        ),
                    )
                    if cache and reader.cacheable:
                        cache.put_reading(ref.key, reader.id, sr.result)
        except Cancelled:
            raise
        except Exception as e:  # 想定外も含めて、この1枚だけ失敗扱いにする
            log.warning("読み取り失敗: %s (%s)", ref.label, type(e).__name__)
            sr.result, sr.error = None, f"読み取り失敗: {e}"
        out[i] = sr
        with lock:
            done += 1
            d = done
        if progress:
            progress(d, total)

    if progress:
        progress(0, total)
    with ThreadPoolExecutor(max_workers=max(1, int(cfg["workers"]))) as ex:
        futures = [ex.submit(work, i) for i in range(total)]
        for f in futures:
            try:
                f.result()
            except Cancelled:
                pass
    if cancel is not None and cancel.is_set():
        raise Cancelled()
    log.info("読み取り完了: %d件（エラー%d件）", total, sum(1 for s in out if s and s.error))
    return [s for s in out if s is not None]
