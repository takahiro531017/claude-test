import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("RETURNS_DATA_DIR", str(tmp_path))
    from app import db
    c = db.connect()
    db.init_db(c)
    yield c
    c.close()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("RETURNS_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        c.cookies.set("staff_name", "%E5%B1%B1%E7%94%B0")  # 山田
        yield c


def ret(**kw):
    d = {"part_no": "ABC-123", "defect": "電源が入らない", "quantity": "1"}
    d.update(kw)
    return d
