from datetime import date

from app import importer, stats
from conftest import ROWS, make_master


def add(conn, d, store, rep):
    conn.execute("INSERT INTO visits(visit_date,store_code,rep_code,memo,created_by,created_at,updated_at) "
                 "VALUES(?,?,?,?,?,?,?)", (d, store, rep, "", rep, "x", "x"))
    conn.commit()


def setup(conn, master):
    importer.import_master(conn, master, "m.xlsx", "t")


def test_same_store_twice_in_month(conn, master):
    setup(conn, master)
    add(conn, "2026-10-01", "10001", "R1")
    add(conn, "2026-10-20", "10001", "R1")
    s = stats.summarize(conn, *stats.month_range("2026-10"))
    assert (s["visits"], s["stores"], s["companies"]) == (2, 1, 1)
    assert s["assigned_stores"] == 6 and s["visited_assigned"] == 1


def test_company_unique(conn, master):
    setup(conn, master)
    add(conn, "2026-10-01", "10001", "R1")
    add(conn, "2026-10-02", "10002", "R1")   # 同じ法人の別店舗
    add(conn, "2026-10-03", "10003", "R1")
    s = stats.summarize(conn, *stats.month_range("2026-10"))
    assert (s["visits"], s["stores"], s["companies"]) == (3, 3, 2)
    comp = {c["company"]: c for c in stats.company_breakdown(conn, *stats.month_range("2026-10"))}
    assert comp["(株)アルファ"]["visited_stores"] == 2 and comp["(株)アルファ"]["assigned_stores"] == 2
    assert comp["ガンマ"]["visits"] == 0


def test_month_boundaries(conn, master):
    setup(conn, master)
    add(conn, "2026-09-30", "10001", "R1")
    add(conn, "2026-10-31", "10001", "R1")
    add(conn, "2026-11-01", "10001", "R1")
    assert stats.summarize(conn, *stats.month_range("2026-10"))["visits"] == 1
    assert stats.month_range("2026-12") == (date(2026, 12, 1), date(2026, 12, 31))
    assert stats.add_months("2026-01", -1) == "2025-12"


def test_by_rep_and_monthly_agree(conn, master):
    setup(conn, master)
    add(conn, "2026-10-01", "10001", "R1")
    add(conn, "2026-10-02", "10004", "R2")
    add(conn, "2026-10-03", "10004", "R2")
    s, e = stats.month_range("2026-10")
    br = stats.by_rep(conn, s, e)
    for r in br["reps"]:
        m = stats.monthly(conn, "2026-10", r["rep_code"])["summary"]
        assert {k: m[k] for k in ("visits", "stores", "assigned_stores")} == \
               {k: r[k] for k in ("visits", "stores", "assigned_stores")}
    assert sum(r["visits"] for r in br["reps"]) == br["total"]["visits"] == 3
    r2 = [r for r in br["reps"] if r["rep_code"] == "R2"][0]
    assert r2["stores"] == 1 and r2["rate"] == round(1 / 3, 4)


def test_reassignment_keeps_history(conn, master, tmp_path):
    setup(conn, master)
    add(conn, "2026-10-01", "10001", "R1")
    rows = [("R2", "架空 二") + r[2:] if r[2] == "10001" else r for r in ROWS]
    p = tmp_path / "m2.xlsx"
    make_master(p, rows)
    rep = importer.import_master(conn, p, "m2.xlsx", "t")
    assert rep["updated_stores"] == 1
    s, e = stats.month_range("2026-10")
    assert stats.summarize(conn, s, e, "R1")["visits"] == 1      # 過去の集計は変わらない
    assert stats.summarize(conn, s, e, "R2")["visits"] == 0
    assert stats.summarize(conn, s, e, "R1")["assigned_stores"] == 2


def test_store_list_last_visit(conn, master):
    setup(conn, master)
    add(conn, "2026-09-01", "10001", "R1")
    add(conn, "2026-09-20", "10001", "R2")   # 別営業の訪問でも最終訪問日は店舗単位
    today = date(2026, 10, 7)
    items = {i["code"]: i for i in stats.store_list(conn, today)}
    assert items["10001"]["last_visit"] == "2026-09-20" and items["10001"]["days"] == 17
    assert items["10002"]["days"] is None
    assert len(stats.store_list(conn, today, unvisited=True)) == 5
    assert [i["code"] for i in stats.store_list(conn, today, min_days=30)] and \
        "10001" not in [i["code"] for i in stats.store_list(conn, today, min_days=30)]
    assert stats.store_list(conn, today)[0]["days"] is None            # 未訪問が最上位
    assert {i["code"] for i in stats.store_list(conn, today, q="北")} == {"10001"}
    assert stats.store_list(conn, today, mine_rep="R2")[0]["rep_code"] == "R2"
    blank = [i for i in stats.store_list(conn, today) if i["code"] == "10005"][0]
    assert blank["display_name"] == "ガンマ"                              # 店舗名空欄は得意先名


def test_trend_12_months(conn, master):
    setup(conn, master)
    add(conn, "2025-11-05", "10001", "R1")
    t = stats.monthly(conn, "2026-10")["trend"]
    assert len(t) == 12 and t[0]["month"] == "2025-11" and t[-1]["month"] == "2026-10"
    assert t[0]["visits"] == 1


def test_company_partial_search(conn, master):
    setup(conn, master)
    today = date(2026, 10, 7)
    codes = {i["code"] for i in stats.store_list(conn, today, company_q="ﾍﾞｰﾀ")}
    assert codes == {"10003", "10004"}                     # 法人名の一部・半角カナでも絞れる
    codes = {i["code"] for i in stats.store_list(conn, today, company_q="ベータ", q="支店")}
    assert codes == {"10004"}                              # 法人 + 店舗名の組み合わせ
