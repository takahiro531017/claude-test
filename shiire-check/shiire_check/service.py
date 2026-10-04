"""GUIから独立した処理の取りまとめ（読み取り→照合→手修正→再照合）。"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from shiire_check import excel_io
from shiire_check.cache import Cache
from shiire_check.config import data_dir
from shiire_check.imaging import collect_pages
from shiire_check.matcher import LedgerRow, ResultRow, SlipInput, match
from shiire_check.normalize import Normalizer
from shiire_check.pipeline import SlipReading, read_all

log = logging.getLogger(__name__)


@dataclass
class ColumnSelection:
    sheet: str | None = None
    header_row: int = 1
    number: int = 0
    maker: int | None = None
    date: int | None = None
    amount: int | None = None


class CheckSession:
    def __init__(self, cfg: dict, cache: Cache | None = None):
        self.cfg = cfg
        self.cache = cache or Cache(data_dir(cfg) / "cache.sqlite3")
        self.norm = Normalizer(cfg["normalize"])
        self.ledger: list[LedgerRow] = []
        self.cols = ColumnSelection()
        self.readings: list[SlipReading] = []
        self.results: list[ResultRow] = []

    def load_ledger(self, path, cols: ColumnSelection) -> int:
        self.cols = cols
        self.ledger = excel_io.read_ledger(
            path, cols.sheet, cols.header_row, cols.number, cols.maker, cols.date, cols.amount
        )
        return len(self.ledger)

    def read_slips(self, folder, reader, progress=None, cancel: threading.Event | None = None) -> None:
        pages = collect_pages(
            Path(folder), self.cfg["scan"]["recursive"], self.cfg["image"]["max_pdf_pages"]
        )
        log.info("伝票ページ数: %d", len(pages))
        self.readings = read_all(pages, reader, self.cache, self.cfg, progress, cancel)
        self.rematch()

    def rematch(self) -> list[ResultRow]:
        corrections = self.cache.get_corrections()
        slips = [
            SlipInput(r.key, r.ref.label, r.ref.path.name, r.result, r.error, corrections.get(r.key))
            for r in self.readings
        ]
        c = self.cols
        self.results = match(
            slips, self.ledger, self.cfg, self.norm,
            use_amount=c.amount is not None, use_date=c.date is not None, use_maker=c.maker is not None,
        )
        states = self.cache.get_states()
        for r in self.results:
            if r.key in states:
                r.confirmed, r.memo = states[r.key]
        return self.results

    def set_correction(self, key: str, number: str | None) -> list[ResultRow]:
        """伝票番号を手修正して保存し、再照合する（空文字なら修正を取り消す）。"""
        self.cache.set_correction(key, (number or "").strip() or None)
        return self.rematch()

    def set_state(self, row: ResultRow, confirmed: bool, memo: str) -> None:
        row.confirmed, row.memo = confirmed, memo
        self.cache.set_state(row.key, confirmed, memo)

    def reading_for(self, key: str) -> SlipReading | None:
        return next((r for r in self.readings if r.key == key), None)

    def export(self, path) -> Path:
        return excel_io.write_results(path, self.results)
