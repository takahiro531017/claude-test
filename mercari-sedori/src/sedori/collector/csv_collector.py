from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from ..models import Item

ON_SALE = {"on_sale", "selling", "販売中", ""}
SOLD = {"sold", "sold_out", "売り切れ", "売却済み"}
BUYER_PAYS = {"buyer", "着払い", "着払い(購入者負担)", "購入者負担"}


def _int(v: str) -> int:
    return int(str(v).replace(",", "").replace("¥", "").replace("円", "").strip() or 0)


class CsvCollector:
    """手動CSV取り込み。列: item_id,title,price,condition,shipping_payer,
    listed_at,url,image_url,status,sold_at[,category,description]"""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _rows(self) -> Iterable[Item]:
        with self.path.open(encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if not (r.get("item_id") or "").strip():
                    continue
                status = (r.get("status") or "").strip().lower()
                yield Item(
                    item_id=r["item_id"].strip(),
                    title=(r.get("title") or "").strip(),
                    price=_int(r.get("price", "0")),
                    condition=(r.get("condition") or "").strip(),
                    shipping_payer="buyer" if (r.get("shipping_payer") or "").strip() in BUYER_PAYS else "seller",
                    listed_at=(r.get("listed_at") or "").strip(),
                    url=(r.get("url") or "").strip(),
                    image_url=(r.get("image_url") or "").strip(),
                    status="sold" if status in SOLD else "on_sale",
                    sold_at=(r.get("sold_at") or "").strip(),
                    category=(r.get("category") or "").strip(),
                    description=(r.get("description") or "").strip(),
                )

    def fetch_active(self) -> Iterable[Item]:
        return [i for i in self._rows() if i.status == "on_sale"]

    def fetch_sold(self) -> Iterable[Item]:
        return [i for i in self._rows() if i.status == "sold"]
