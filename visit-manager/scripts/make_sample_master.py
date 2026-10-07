"""開発・動作確認用の【架空】マスタを作る。実データは一切含まない。

使い方: python scripts/make_sample_master.py data/sample_master.xlsx
"""
import random
import sys

import openpyxl

REPS = [("1A1", "架空 太郎"), ("1A2", "架空 花子"), ("1B1", "試験 一郎"), ("1B2", "試験 二郎"),
        ("2A1", "見本 三郎"), ("2A2", "見本 梅子"), ("2B1", "仮名 四郎")]
COMPANIES = ["(株)サンプル電機", "テスト商事(株)", "(株)ダミーHD", "ダミー(株)", "サンプルマート", "サンプル",
             "(株)ユニット家電", "ゆうれい電器", "(株)ほげ堂", "ふが無線"]
SHORT = ["サンプル", "テスト", "ダミー", "ダミー", "サンプル", "サンプル", "ユニット", "ゆうれい", "ほげ", "ふが"]
PLACES = ["北本店", "南本店", "東店", "西店", "中央店", "駅前店", "港店", "山手店", "郊外店", "新町店"]


def build(path: str, seed: int = 1) -> None:
    rnd = random.Random(seed)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "担当店舗マスタ"
    ws.append(["営業コード", "営業担当者", "得意先コード", "得意先名", "店舗名"])
    n = 10000
    for ci, comp in enumerate(COMPANIES):
        for pi, place in enumerate(PLACES):
            if rnd.random() < 0.35:
                continue
            n += 1
            rep = REPS[(ci + pi) % len(REPS)]
            ws.append([rep[0], rep[1], str(n), comp, "" if (ci, pi) == (7, 0) else f"{SHORT[ci]}{place}"])
    ws.append([REPS[0][0], REPS[0][1], "00123", "(株)先頭ゼロ", "架空店"])  # 先頭0のコード
    wb.save(path)


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "data/sample_master.xlsx")
