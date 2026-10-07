from app import importer
from conftest import ROWS, make_master


def test_import_basic_and_reimport(conn, master):
    r = importer.import_master(conn, master, "m.xlsx", "t")
    assert r["new_stores"] == 6 and r["blank_store_names"] == 1 and len(r["new_users"]) == 2
    r2 = importer.import_master(conn, master, "m.xlsx", "t")
    assert r2["unchanged_stores"] == 6 and r2["new_users"] == []


def test_codes_are_strings_and_zero_padded(conn, tmp_path):
    p = tmp_path / "z.xlsx"
    make_master(p, [("R1", "架空", 123, "(株)ゼロ", "店")])   # 数値セルで入っていた場合
    r = importer.import_master(conn, p, "z.xlsx", "t")
    assert r["padded_codes"] == 1
    assert conn.execute("SELECT code FROM stores").fetchone()["code"] == "00123"


def test_duplicates_reported_not_deleted(conn, tmp_path):
    p = tmp_path / "d.xlsx"
    make_master(p, ROWS + [("R1", "架空 一", "10001", "(株)アルファ", "重複店")])
    r = importer.import_master(conn, p, "d.xlsx", "t")
    assert len(r["duplicates"]) == 1 and r["duplicates"][0]["code"] == "10001"
    assert conn.execute("SELECT COUNT(*) c FROM stores").fetchone()["c"] == 6


def test_removed_store_deactivated_visits_kept(conn, master, tmp_path):
    importer.import_master(conn, master, "m.xlsx", "t")
    conn.execute("INSERT INTO visits VALUES(NULL,'2026-10-01','10006','R2','','R2','x','x')")
    p = tmp_path / "m2.xlsx"
    make_master(p, ROWS[:5])
    r = importer.import_master(conn, p, "m2.xlsx", "t")
    assert r["deactivated_stores"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM visits").fetchone()["c"] == 1


def test_missing_column(conn, tmp_path):
    import openpyxl, pytest
    p = tmp_path / "bad.xlsx"
    wb = openpyxl.Workbook(); wb.active.append(["a", "b"]); wb.save(p)
    with pytest.raises(importer.ImportError_):
        importer.import_master(conn, p, "bad.xlsx", "t")


def test_name_candidates(conn, tmp_path):
    p = tmp_path / "n.xlsx"
    make_master(p, [("R1", "架空", "1", "(株)ニセ商店", "a"), ("R1", "架空", "2", "ニセ商店(株)", "b"),
                    ("R1", "架空", "3", "ダミー", "c"), ("R1", "架空", "4", "ダミーマート", "d"),
                    ("R1", "架空", "5", "無関係", "e")])
    importer.import_master(conn, p, "n.xlsx", "t")
    g = importer.name_candidates(conn)
    sets = [{n["name"] for n in x["names"]} for x in g]
    assert {"(株)ニセ商店", "ニセ商店(株)"} in sets and {"ダミー", "ダミーマート"} in sets
    assert all("無関係" not in s for s in sets)
