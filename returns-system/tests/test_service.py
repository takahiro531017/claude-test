from datetime import date

import pytest
from conftest import ret

from app import service
from app.service import BusinessError

D = date(2026, 10, 8)


def test_receipt_numbering_per_day(conn):
    a = service.create_return(conn, ret(), "山田", today=D)
    b = service.create_return(conn, ret(), "山田", today=D)
    c = service.create_return(conn, ret(received_on="2026-10-09"), "山田", today=D)
    assert (a["receipt_no"], b["receipt_no"]) == ("RT-20261008-001", "RT-20261008-002")
    assert c["receipt_no"] == "RT-20261009-001"  # 日が変わると001に戻る


def test_receipt_numbering_unique_across_connections(tmp_path, monkeypatch):
    monkeypatch.setenv("RETURNS_DATA_DIR", str(tmp_path))
    from app import db
    c1, c2 = db.connect(), db.connect()
    db.init_db(c1)
    nos = [service.create_return(c, ret(), "山田", today=D)["receipt_no"] for c in (c1, c2, c1, c2)]
    assert len(set(nos)) == 4 and nos[-1] == "RT-20261008-004"


def test_required_fields(conn):
    with pytest.raises(BusinessError, match="品番"):
        service.create_return(conn, ret(part_no="  "), "山田")
    with pytest.raises(BusinessError, match="不良内容"):
        service.create_return(conn, ret(defect=""), "山田")
    with pytest.raises(BusinessError, match="数量"):
        service.create_return(conn, ret(quantity="0"), "山田")
    with pytest.raises(BusinessError, match="数量"):
        service.create_return(conn, ret(quantity="あ"), "山田")
    assert conn.execute("SELECT COUNT(*) FROM returns").fetchone()[0] == 0  # 失敗時はマスタも増えない
    assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0


def test_optional_fields_can_be_blank(conn):
    res = service.create_return(conn, ret(), "山田")
    r = service.get_return(conn, res["id"])
    assert r["customer_name"] is None and r["maker_name"] is None and r["serial_no"] == ""
    assert r["status"] == "received" and r["print_status"] == "unprinted"


def test_status_flow_and_history(conn):
    rid = service.create_return(conn, ret(), "山田")["id"]
    with pytest.raises(BusinessError, match="1段階"):
        service.change_status(conn, rid, "decided", "山田")
    service.change_status(conn, rid, "checking", "山田")
    with pytest.raises(BusinessError, match="処分方法"):
        service.change_status(conn, rid, "decided", "山田")
    service.set_disposition(conn, rid, "recycle", "山田")
    service.change_status(conn, rid, "decided", "佐藤")
    service.set_disposition(conn, rid, "discard", "佐藤")  # 直らなかった→廃棄
    service.change_status(conn, rid, "done", "佐藤")
    r = service.get_return(conn, rid)
    assert r["status"] == "done" and r["disposition"] == "discard" and r["closed_at"]
    with pytest.raises(BusinessError):
        service.set_disposition(conn, rid, "recycle", "山田")  # 完了後は変更不可
    service.change_status(conn, rid, "decided", "佐藤")  # 1段階戻せる
    assert service.get_return(conn, rid)["closed_at"] is None
    ev = [(e["actor"], e["action"], e["from_value"], e["to_value"]) for e in reversed(service.events_of(conn, rid))]
    assert ev[0][:2] == ("山田", "create")
    assert ("山田", "disposition", "", "リサイクル販売") in ev
    assert ("佐藤", "disposition", "リサイクル販売", "廃棄") in ev
    assert ("佐藤", "status", "処分決定済", "完了") in ev


def test_disposition_requires_checking(conn):
    rid = service.create_return(conn, ret(), "山田")["id"]
    with pytest.raises(BusinessError):
        service.set_disposition(conn, rid, "discard", "山田")
    with pytest.raises(BusinessError):
        service.set_disposition(conn, rid, "bogus", "山田")


def test_update_records_changes(conn):
    rid = service.create_return(conn, ret(), "山田")["id"]
    service.update_return(conn, rid, ret(product_name="ケトル", maker="ダミー電機", serial_no="SN1"), "佐藤")
    r = service.get_return(conn, rid)
    assert (r["product_name"], r["maker_name"], r["serial_no"]) == ("ケトル", "ダミー電機", "SN1")
    e = service.events_of(conn, rid)[0]
    assert e["action"] == "edit" and e["actor"] == "佐藤" and "商品名" in e["note"] and "メーカー" in e["note"]


def test_find_by_receipt_no_variants(conn):
    res = service.create_return(conn, ret(), "山田", today=D)
    for q in ["RT-20261008-001", "rt-20261008-001", "ＲＴ－２０２６１００８－００１", "20261008-001", "1"]:
        assert service.find_by_receipt_no(conn, q, today=D)["id"] == res["id"], q
    assert service.find_by_receipt_no(conn, "RT-20261008-999") is None


def test_list_filters_and_stale(conn):
    old = service.create_return(conn, ret(part_no="OLD-1", customer="A商事", maker="M社"), "山田", today=D)
    service.create_return(conn, ret(part_no="NEW-1"), "山田", today=date.today())
    conn.execute("UPDATE returns SET received_on='2026-09-01' WHERE id=?", (old["id"],))
    rows, total = service.list_returns(conn, {"part_no": "old1"})
    assert total == 1 and rows[0]["part_no_text"] == "OLD-1"
    assert service.list_returns(conn, {"maker": "m社"})[1] == 1
    assert service.list_returns(conn, {"customer": "ａ商事"})[1] == 1
    assert service.list_returns(conn, {"date_from": "2026/09/01", "date_to": "2026/09/30"})[1] == 1
    assert service.stale_level(conn, rows[0], today=date(2026, 10, 8)) == "over"  # 14日超
    assert service.stale_level(conn, rows[0], today=date(2026, 9, 10)) == "warn"  # 7日以上
    assert service.stale_level(conn, rows[0], today=date(2026, 9, 2)) == ""


def test_mark_printed(conn):
    rid = service.create_return(conn, ret(), "山田")["id"]
    service.mark_printed(conn, [rid], "山田")
    service.mark_printed(conn, [rid], "山田")
    r = service.get_return(conn, rid)
    assert r["print_status"] == "printed" and r["print_count"] == 2
    assert service.list_returns(conn, {"unprinted": True})[1] == 0
