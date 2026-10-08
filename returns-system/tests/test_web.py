import io

from PIL import Image
from conftest import ret


def _post(client, **kw):
    return client.post("/api/returns", data=ret(**kw))


def test_requires_staff_cookie(client):
    client.cookies.clear()
    r = client.get("/new", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/staff")
    assert client.post("/api/returns", data=ret()).status_code == 401


def test_staff_select_sets_cookie(client):
    client.cookies.clear()
    r = client.post("/staff", data={"name": "ｔａｎａｋａ", "next": "/new"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/new"
    assert "staff_name" in r.headers["set-cookie"]


def test_register_then_detail_and_qr_url(client):
    res = _post(client, customer="ダミー商事", product_name="ケトル").json()
    assert res["ok"] and res["receipt_no"].startswith("RT-")
    page = client.get(f"/r/{res['receipt_no']}")
    assert page.status_code == 200 and "ダミー商事" in page.text
    pr = client.get(f"/print/{res['receipt_no']}")
    assert "<svg" in pr.text and "返品受付票" in pr.text


def test_register_error_message(client):
    r = _post(client, part_no="")
    assert r.status_code == 400 and "品番" in r.json()["error"]


def test_status_change_via_web(client):
    no = _post(client).json()["receipt_no"]
    client.post(f"/r/{no}/status", data={"status": "checking"})
    r = client.post(f"/r/{no}/disposition", data={"disposition": "maker_return"}, follow_redirects=True)
    assert "メーカー返品" in r.text
    r = client.post(f"/r/{no}/status", data={"status": "done"}, follow_redirects=True)
    assert "1段階" in r.text  # 飛ばしはエラー表示


def test_photo_is_shrunk(client, tmp_path):
    img = Image.new("RGB", (4000, 3000), "red")
    buf = io.BytesIO(); img.save(buf, "JPEG")
    res = client.post("/api/returns", data=ret(), files=[("photos", ("a.jpg", buf.getvalue(), "image/jpeg"))]).json()
    page = client.get(f"/r/{res['receipt_no']}").text
    path = page.split('href="/photos/')[1].split('"')[0]
    saved = client.get("/photos/" + path)
    assert saved.status_code == 200
    w, h = Image.open(io.BytesIO(saved.content)).size
    assert max(w, h) == 1280
    assert client.get("/photos/../returns.sqlite3").status_code in (404, 422)


def test_bad_photo_does_not_block_registration(client):
    res = client.post("/api/returns", data=ret(), files=[("photos", ("a.jpg", b"not an image", "image/jpeg"))]).json()
    assert res["ok"] and res["warnings"]


def test_suggest_api_and_product_lookup(client):
    _post(client, part_no="KT-1000", product_name="電気ケトル", maker="ダミー電機")
    assert client.get("/api/suggest", params={"kind": "product", "q": "kt"}).json()[0]["part_no"] == "KT-1000"
    p = client.get("/api/product", params={"part_no": "ｋｔ１０００"}).json()
    assert p["name"] == "電気ケトル" and p["maker"] == "ダミー電機"
    assert client.get("/api/suggest", params={"kind": "defect", "q": ""}).json()  # 初期候補


def test_pdf_endpoints_and_batch(client):
    ids = [_post(client).json()["id"] for _ in range(3)]
    q = ",".join(map(str, ids))
    assert client.get(f"/print/batch.pdf?ids={q}&layout=a4_2up").content.startswith(b"%PDF")
    assert "返品受付票" in client.get(f"/print/batch?ids={q}&layout=a4_2up").text
    client.post("/api/printed", json={"ids": ids})
    assert "印刷済み" in client.get("/print-queue?show=all").text
    assert "未印刷の受付票はありません" in client.get("/print-queue").text


def test_list_and_home(client):
    _post(client, part_no="ZZ-9")
    assert "ZZ-9" in client.get("/returns?q=zz9").text
    assert client.get("/returns?date_from=bad").status_code == 200  # 不正な日付でも落ちない
    assert client.get("/").status_code == 200
    assert client.get("/find?no=nothing", follow_redirects=False).status_code == 303
