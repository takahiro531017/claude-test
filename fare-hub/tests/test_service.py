import sqlite3
from datetime import date

import pytest

from app import db, service
from app.exporter import to_csv
from tools.make_dummy_pdfs import Spec, build_pdf, default_specs, make_rates

from .conftest import TODAY


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.sqlite")
    yield c
    c.close()


def load(conn, st, specs=None):
    return [service.import_pdf(conn, st, f"{s.origin}.pdf", build_pdf(s)) for s in (specs or default_specs())]


def test_import_and_missing(conn, st):
    a, b, c = load(conn, st)
    assert (a["status"], a["cells"], a["missing"]) == ("ok", 132, 0)
    assert c["missing"] == 3 and {(m["region"], m["size"]) for m in service.missing_cells(conn, st, c["tariff_id"])} == {("関東", 100), ("北海道", 260), ("四国", 60)}


def test_duplicate_and_reimport_replace(conn, st):
    load(conn, st)
    assert load(conn, st, [default_specs()[0]])[0]["status"] == "duplicate"  # 同一ファイル
    changed = Spec("拠点A", seed=77)  # 同一拠点・同一適用期日 → 置換
    r = service.import_pdf(conn, st, "a2.pdf", build_pdf(changed))
    assert r["status"] == "ok"
    assert conn.execute("SELECT COUNT(*) FROM tariffs WHERE origin='拠点A'").fetchone()[0] == 1


def test_expiry_status(st):
    t = lambda vf, vt: service.status_of(vf, vt, date(2025, 10, 1), 30)
    assert t("2025-04-01", "2026-03-31") == "active"
    assert t("2025-04-01", "2025-10-20") == "expiring"
    assert t("2024-04-01", "2025-03-31") == "expired"
    assert t("2025-11-01", "2026-03-31") == "upcoming"
    assert t(None, None) == "unknown"


def test_current_tariff_prefers_valid_over_expired(conn, st):
    old = Spec("拠点A", valid_from="2023年4月1日", valid_to="2024年3月31日", seed=5)
    load(conn, st, [old, default_specs()[0]])
    cur = {t["origin"]: t for t in service.current_tariffs(conn, st, TODAY)}
    assert cur["拠点A"]["status"] == "active"


def test_combined_has_one_row_per_origin_region_size(conn, st):
    load(conn, st)
    rows = service.combined_rows(conn, st, TODAY)
    assert len(rows) == 3 * 12 * 11
    truth = make_rates(default_specs()[0])
    a = {(r["region"], r["size"]): r["price"] for r in rows if r["origin"] == "拠点A"}
    assert a == truth


def test_lookup_by_prefecture_and_cheapest_ignores_expired(conn, st):
    load(conn, st)
    out = service.lookup(conn, st, TODAY, "東京都", 100, None)
    assert out["destination"]["region"] == "関東"
    by = {r["origin"]: r for r in out["results"]}
    assert by["拠点C"]["status"] == "expired"
    valid = [by[o]["prices"]["100"] for o in ("拠点A", "拠点B")]
    assert out["cheapest"]["100"] == min(valid)
    assert service.lookup(conn, st, TODAY, "京都", None, None)["destination"]["region"] == "関西"
    assert service.lookup(conn, st, TODAY, "北海道", None, None)["destination"]["region"] == "北海道"
    assert service.lookup(conn, st, TODAY, "沖縄", None, None)["destination"]["special"] is True
    assert service.lookup(conn, st, TODAY, "どこか", None, None)["results"] == []


def test_manual_fix_and_validation(conn, st):
    cid = load(conn, st)[2]["tariff_id"]
    service.set_rate(conn, st, cid, "関東", 100, 321)
    t = service.get_tariff(conn, st, cid, TODAY)
    assert t["rates"]["関東"]["100"] == {"price": 321, "source": "manual"} and len(t["missing"]) == 2
    with pytest.raises(ValueError):
        service.set_rate(conn, st, cid, "関東", 100, -5)
    with pytest.raises(ValueError):
        service.set_rate(conn, st, cid, "火星", 100, 5)
    service.update_meta(conn, cid, {"valid_to": "2030-01-01"})
    assert service.get_tariff(conn, st, cid, TODAY)["status"] == "active"
    with pytest.raises(ValueError):
        service.update_meta(conn, cid, {"valid_to": "来年"})


def test_csv_injection_is_neutralised(conn, st):
    service.import_pdf(conn, st, "x.pdf", build_pdf(Spec("=cmd|'/c calc'!A1", seed=9)))
    assert "'=cmd" in to_csv(conn, st, TODAY).decode("utf-8-sig")
