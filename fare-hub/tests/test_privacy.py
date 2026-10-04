import logging

from tools import selfcheck
from tools.make_dummy_pdfs import NOTES, Spec, build_pdf, make_rates

from .conftest import pdf_files


def test_no_network_code_or_urls():
    assert selfcheck.check_no_network() == []


def test_pii_patterns_absent():
    assert selfcheck.check_pii_patterns() == []


def test_gitignore_effective():
    assert selfcheck.check_git_ignore() == []


def test_logs_contain_no_tariff_content(client, caplog):
    sp = Spec("拠点機密ダミー", seed=4)
    with caplog.at_level(logging.DEBUG):
        client.post("/api/import", files=[("files", ("a.pdf", build_pdf(sp), "application/pdf"))])
        client.post("/api/import", files=[("files", ("b.pdf", b"%PDF-1.4 SECRET-PAYLOAD", "application/pdf"))])
    log = "\n".join(r.getMessage() for r in caplog.records)
    assert "a.pdf" in log and "b.pdf" in log  # ファイル名とエラー種別は出す
    assert "拠点機密ダミー" not in log and "SECRET-PAYLOAD" not in log
    assert not any(n[:10] in log for n in NOTES)  # 注記本文
    assert not any(str(p) in log.split() for p in make_rates(sp).values())  # 運賃額


def test_uploaded_pdf_is_not_stored(client, tmp_path):
    client.post("/api/import", files=pdf_files()[:1])
    assert not list(tmp_path.rglob("*.pdf"))
