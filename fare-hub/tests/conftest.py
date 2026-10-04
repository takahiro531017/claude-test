import socket
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app
from tools.make_dummy_pdfs import Spec, build_pdf, default_specs

TODAY = date(2025, 10, 1)  # 拠点A,B=有効 / 拠点C=期限切れ（ダミー仕様）


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    """テスト中、ループバック以外への接続を禁止（外部通信が無いことの検証）。"""
    real = socket.socket.connect

    def guarded(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "::1", "localhost") and not str(host).startswith("/"):
            raise AssertionError("external network access attempted")
        return real(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: (_ for _ in ()).throw(AssertionError("DNS lookup attempted")))


@pytest.fixture(scope="session")
def st():
    return load_settings()


@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=tmp_path / "t.sqlite", today=TODAY, allowed_hosts={"testserver"})
    return TestClient(app)


def pdf_files(specs=None):
    return [("files", (f"{s.origin}.pdf", build_pdf(s), "application/pdf")) for s in (specs or default_specs())]


@pytest.fixture
def loaded(client):
    r = client.post("/api/import", files=pdf_files())
    assert r.status_code == 200
    return client
