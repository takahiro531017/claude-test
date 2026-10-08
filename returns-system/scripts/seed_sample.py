"""ダミーの返品データを投入する(マスタは入力から自動蓄積される)。

使い方:  python scripts/seed_sample.py            ← data/ に投入
         python scripts/seed_sample.py --reset    ← 既存データを消して入れ直す
実在の個人・取引先とは無関係の架空データです。
"""
import argparse
import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config, db, service  # noqa: E402

CUSTOMERS = ["ダミー商事", "サンプル電器店", "テスト家電販売", "ＤＵＭＭＹ商会", "サンプル電器店 "]  # 表記ゆれ入り
PRODUCTS = [  # (品番, 商品名, メーカー)
    ("KT-1000", "電気ケトル 1.0L", "ダミー電機"), ("kt-1000", "電気ケトル 1.0L", "ダミー電機"),
    ("RC-550", "炊飯器 5.5合", "サンプル工業"), ("HD-20", "ヘアドライヤー", "テスト産業"),
    ("VC-300", "掃除機 サイクロン", "ダミー電機"), ("FN-35", "扇風機 35cm", "サンプル工業"),
    ("MW-2000", "電子レンジ 20L", "テスト産業"), ("ＬＥ－８０", "LEDスタンド", "ダミー電機"),
    ("TS-200", "トースター", ""), ("HM-10", "加湿器", "サンプル工業"),
]
DEFECTS = ["電源が入らない", "動作しない", "異音がする", "破損", "外観キズ", "部品欠品", "水濡れ", "初期不良", "スイッチ不良"]
STAFF = ["山田", "佐藤", "鈴木"]


def seed(conn, n: int = 40, seed_value: int = 1):
    rnd = random.Random(seed_value)
    today = date.today()
    made = []
    for _ in range(n):
        on = today - timedelta(days=rnd.randint(0, 45))
        part, name, maker = rnd.choice(PRODUCTS)
        res = service.create_return(conn, {
            "customer": rnd.choice(CUSTOMERS), "part_no": part, "product_name": name, "maker": maker,
            "serial_no": f"SN{rnd.randint(100000, 999999)}" if rnd.random() < .7 else "",
            "quantity": rnd.choice([1, 1, 1, 2, 3]), "defect": rnd.choice(DEFECTS),
            "reason_note": rnd.choice(["", "", "お客様都合ではない", "箱に傷あり"]),
            "received_on": on.isoformat(), "staff": rnd.choice(STAFF),
        }, rnd.choice(STAFF))
        made.append(res["id"])
    # 状況をいろいろに進める
    for rid in made:
        step = rnd.choice([0, 0, 1, 2, 3, 3])
        disp = rnd.choice(service.DISPOSITIONS)
        if step >= 1:
            service.change_status(conn, rid, "checking", "山田")
        if step >= 2:
            service.set_disposition(conn, rid, disp, "山田")
            service.change_status(conn, rid, "decided", "山田")
        if step >= 3:
            service.change_status(conn, rid, "done", "佐藤")
    service.mark_printed(conn, made[: n // 2], "山田")
    return made


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("-n", type=int, default=40)
    a = ap.parse_args()
    if a.reset:
        for p in config.data_dir().glob("returns.sqlite3*"):
            p.unlink()
    conn = db.connect()
    db.init_db(conn)
    ids = seed(conn, a.n)
    print(f"{len(ids)}件のダミーデータを投入しました({config.db_path()})")
