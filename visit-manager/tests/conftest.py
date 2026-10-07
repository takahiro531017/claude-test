import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402


def make_master(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["営業コード", "営業担当者", "得意先コード", "得意先名", "店舗名"])
    for r in rows:
        ws.append(list(r))
    wb.save(path)


# 架空データ: 営業2名、法人3社、店舗6つ
ROWS = [
    ("R1", "架空 一", "10001", "(株)アルファ", "北店"),
    ("R1", "架空 一", "10002", "(株)アルファ", "南店"),
    ("R1", "架空 一", "10003", "ベータ商事", "本店"),
    ("R2", "架空 二", "10004", "ベータ商事", "支店"),
    ("R2", "架空 二", "10005", "ガンマ", ""),
    ("R2", "架空 二", "10006", "ガンマ", "東店"),
]


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.init_db(c)
    yield c
    c.close()


@pytest.fixture
def master(tmp_path):
    p = tmp_path / "m.xlsx"
    make_master(p, ROWS)
    return p
