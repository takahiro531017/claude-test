import pytest
from fastapi.testclient import TestClient

from app import config, db, importer, main
from conftest import ROWS, make_master


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    from app import auth
    auth._fails.clear()
    with TestClient(main.app) as c:
        conn = db.connect()
        make_master(tmp_path / "m.xlsx", ROWS)
        rep = importer.import_master(conn, tmp_path / "m.xlsx", "m.xlsx", "t")
        conn.close()
        yield c, {u["id"]: u["temp_password"] for u in rep["new_users"]}, tmp_path


def login(c, uid, pw):
    return c.post("/api/auth/login", json={"id": uid, "password": pw})


def ready(env, uid="R1", newpw="Passw0rd-x"):
    c, pws, _ = env
    assert login(c, uid, pws[uid]).status_code == 200
    r = c.post("/api/auth/change-password", json={"old_password": pws[uid], "new_password": newpw})
    assert r.status_code == 200, r.text
    return c


def test_unauthenticated_gets_nothing(env):
    c, _, _ = env
    for path in ["/api/meta", "/api/stores", "/api/stores/10001", "/api/visits", "/api/stats/monthly",
                 "/api/stats/by-rep?month=2026-10", "/api/stats/rep/R1?month=2026-10", "/api/admin/users",
                 "/api/admin/name-candidates", "/api/stats/by-rep/csv?month=2026-10", "/api/auth/me"]:
        assert c.get(path).status_code == 401, path
    assert c.post("/api/visits", json={"visit_date": "2026-10-01", "store_code": "10001"}).status_code == 401
    assert c.post("/api/admin/import", files={"file": ("a.xlsx", b"x")}).status_code == 401


def test_must_change_password_blocks_data(env):
    c, pws, _ = env
    login(c, "R1", pws["R1"])
    assert c.get("/api/stores").status_code == 403
    assert c.get("/api/auth/me").json()["must_change"] is True
    assert c.post("/api/auth/change-password", json={"old_password": pws["R1"], "new_password": "short"}).status_code == 400
    ready(env)
    assert c.get("/api/stores").status_code == 200


def test_login_wrong_password_and_lock(env):
    c, pws, _ = env
    for _ in range(5):
        assert login(c, "R2", "bad").status_code == 401
    assert login(c, "R2", pws["R2"]).status_code == 429


def test_visit_rules(env):
    c = ready(env)
    today = c.get("/api/meta").json()["today"]
    r = c.post("/api/visits", json={"visit_date": today, "store_code": "10001", "memo": "テスト"})
    assert r.status_code == 201
    r = c.post("/api/visits", json={"visit_date": today, "store_code": "10001"})   # 重複
    assert r.status_code == 409 and r.json()["detail"]["code"] == "duplicate"
    assert c.post("/api/visits", json={"visit_date": today, "store_code": "10001", "force": True}).status_code == 201
    r = c.post("/api/visits", json={"visit_date": "2999-01-01", "store_code": "10002"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "future"
    assert c.post("/api/visits", json={"visit_date": "bad", "store_code": "10002"}).status_code == 400
    # 他人名義では登録できない
    assert c.post("/api/visits", json={"visit_date": today, "store_code": "10004", "rep_code": "R2"}).status_code == 403


def test_edit_delete_only_own_or_admin(env):
    c, pws, _ = env
    c1 = ready(env, "R1")
    vid = c1.post("/api/visits", json={"visit_date": "2026-10-01", "store_code": "10001"}).json()["id"]
    c1.post("/api/auth/logout")
    c2 = ready(env, "R2")
    assert c2.put(f"/api/visits/{vid}", json={"visit_date": "2026-10-02", "store_code": "10001"}).status_code == 403
    assert c2.delete(f"/api/visits/{vid}").status_code == 403
    items = c2.get("/api/visits").json()["items"]
    assert items[0]["editable"] is False                           # 閲覧は全員可
    assert c2.get("/api/stats/by-rep?month=2026-10").status_code == 200
    assert c2.get("/api/stats/by-rep/csv?month=2026-10").status_code == 403   # CSVは管理者のみ
    assert c2.post("/api/admin/import", files={"file": ("a.xlsx", b"x")}).status_code == 403
    c2.post("/api/auth/logout")
    # 管理者は編集・削除できる
    import re
    admin_pw = _admin_pw(env)
    assert login(c2, "admin", admin_pw).status_code == 200
    c2.post("/api/auth/change-password", json={"old_password": admin_pw, "new_password": "Adm1nPass-x"})
    assert c2.put(f"/api/visits/{vid}", json={"visit_date": "2026-10-03", "store_code": "10001"}).status_code == 200
    r = c2.get("/api/stats/by-rep/csv?month=2026-10")
    assert r.status_code == 200 and r.content.startswith("﻿".encode())
    assert c2.delete(f"/api/visits/{vid}").status_code == 200


def _admin_pw(env):
    c, _, _ = env
    conn = db.connect()
    from app import auth
    pw = auth.temp_password()
    conn.execute("UPDATE users SET password_hash=?, must_change=1 WHERE id='admin'", (auth.hash_password(pw),))
    conn.commit(); conn.close()
    return pw


def test_screens_agree(env):
    c = ready(env)
    for d in ("2026-10-01", "2026-10-09"):
        c.post("/api/visits", json={"visit_date": d, "store_code": "10001", "force": True})
    m = c.get("/api/stats/monthly?month=2026-10&rep=R1").json()["summary"]
    b = [r for r in c.get("/api/stats/by-rep?month=2026-10").json()["reps"] if r["rep_code"] == "R1"][0]
    assert (m["visits"], m["stores"]) == (b["visits"], b["stores"]) == (2, 1)
    d = c.get("/api/stats/rep/R1?month=2026-10").json()
    assert len(d["visits"]) == 2


def test_security_headers(env):
    c, _, _ = env
    r = c.get("/")
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert c.get("/api/meta").headers["cache-control"] == "no-store"


def test_manual_visit_for_store_not_in_list(env):
    c = ready(env)
    today = c.get("/api/meta").json()["today"]
    r = c.post("/api/visits", json={"visit_date": today, "manual_company": "架空リスト外商事", "manual_name": "新規店"})
    assert r.status_code == 201
    r = c.post("/api/visits", json={"visit_date": today, "manual_company": "架空リスト外商事", "manual_name": "新規店"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "duplicate"      # 同じ訪問先は同じ扱い
    assert c.post("/api/visits", json={"visit_date": today}).status_code == 400    # 店舗も手入力もない
    items = c.get("/api/visits").json()["items"]
    assert items[0]["manual"] == 1 and items[0]["display_name"] == "新規店"
    m = c.get(f"/api/stats/monthly?month={today[:7]}").json()
    assert m["summary"]["visits"] == 1 and m["summary"]["assigned_stores"] == 6      # 担当店舗数は増えない
    assert all(s["code"] != items[0]["store_code"] for s in c.get("/api/stores").json()["items"])
    assert "架空リスト外商事" not in c.get("/api/meta").json()["companies"]
    # マスタ再取り込みでも、手入力の訪問先と訪問は消えない
    conn = db.connect()
    importer.import_master(conn, env[2] / "m.xlsx", "m.xlsx", "t"); conn.close()
    assert len(c.get("/api/visits").json()["items"]) == 1
    assert c.get(f"/api/stores/{items[0]['store_code']}").status_code == 200
