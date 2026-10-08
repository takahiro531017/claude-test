from conftest import ret

from app import masters, service


def test_auto_accumulate_and_dedupe(conn):
    service.create_return(conn, ret(customer="ダミー商事", maker="ダミー電機", product_name="ケトル"), "山田")
    service.create_return(conn, ret(part_no="ａｂｃ 123", customer="ダミー　商事", maker="ダミー電機 "), "山田")
    assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM makers").fetchone()[0] == 1
    p = conn.execute("SELECT * FROM products").fetchone()
    assert p["use_count"] == 2 and p["part_no"] == "ABC-123"
    assert conn.execute("SELECT use_count FROM customers").fetchone()[0] == 2


def test_new_master_is_unreviewed(conn):
    service.create_return(conn, ret(customer="新規商事"), "山田")
    assert conn.execute("SELECT is_reviewed FROM customers WHERE name='新規商事'").fetchone()[0] == 0
    # 初期の不良内容候補は確認済み
    assert conn.execute("SELECT is_reviewed FROM defect_types WHERE name='破損'").fetchone()[0] == 1


def test_product_fills_name_and_maker_later(conn):
    service.create_return(conn, ret(), "山田")  # 商品名・メーカー不明で登録できる
    service.create_return(conn, ret(product_name="ケトル", maker="ダミー電機"), "山田")
    p = masters.find_product(conn, "abc123")
    assert p["name"] == "ケトル" and p["maker"] == "ダミー電機"


def test_same_part_different_name_warns_but_saves(conn):
    service.create_return(conn, ret(product_name="ケトル"), "山田")
    res = service.create_return(conn, ret(product_name="トースター"), "山田")
    assert res["warnings"] and "ケトル" in res["warnings"][0]
    p = conn.execute("SELECT * FROM products").fetchone()
    assert p["name"] == "ケトル" and p["name_conflict"] == 1 and p["is_reviewed"] == 0
    r = service.find_by_receipt_no(conn, res["receipt_no"])
    assert r["product_name"] == "トースター"  # 返品データには入力どおり残る


def test_suggest_matches_across_width_and_case(conn):
    service.create_return(conn, ret(part_no="KT-1000", product_name="電気ケトル", customer="ダミー商事"), "山田")
    service.create_return(conn, ret(part_no="RC-550", product_name="炊飯器"), "山田")
    assert [s["part_no"] for s in masters.suggest(conn, "product", "ｋｔ")] == ["KT-1000"]
    assert [s["part_no"] for s in masters.suggest(conn, "product", "kt1000")] == ["KT-1000"]
    assert [s["part_no"] for s in masters.suggest(conn, "product", "炊飯")] == ["RC-550"]
    assert [s["name"] for s in masters.suggest(conn, "customer", "ﾀﾞﾐｰ")] == ["ダミー商事"]  # 半角カナでも一致
