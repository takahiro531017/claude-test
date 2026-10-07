"""集計ロジック。月別・営業別・店舗一覧はすべてここの関数を共有する(画面間で数字がずれないように)。

- 訪問は visits.rep_code(訪問した時点の営業)で集計する。担当替えしても過去は変わらない。
- 訪問率 = (その営業の担当店舗のうち期間内に訪問のあった店舗数) / (担当店舗数)。
  営業を指定しない場合は有効な全店舗が分母。
"""
import unicodedata
from datetime import date, timedelta


def month_range(ym: str) -> tuple[date, date]:
    y, m = int(ym[:4]), int(ym[5:7])
    start = date(y, m, 1)
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return start, nxt - timedelta(days=1)


def add_months(ym: str, n: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    i = y * 12 + (m - 1) + n
    return f"{i // 12:04d}-{i % 12 + 1:02d}"


def summarize(conn, start: date, end: date, rep: str | None = None) -> dict:
    where, p = "v.visit_date BETWEEN ? AND ?", [start.isoformat(), end.isoformat()]
    if rep:
        where += " AND v.rep_code=?"
        p.append(rep)
    row = conn.execute(
        f"SELECT COUNT(*) visits, COUNT(DISTINCT v.store_code) stores, COUNT(DISTINCT s.company) companies "
        f"FROM visits v JOIN stores s ON s.code=v.store_code WHERE {where}", p).fetchone()
    sp = [rep] if rep else []
    sw = "AND rep_code=?" if rep else ""
    assigned = conn.execute(f"SELECT COUNT(*) c FROM stores WHERE active=1 {sw}", sp).fetchone()["c"]
    vis_in = conn.execute(
        f"SELECT COUNT(DISTINCT v.store_code) c FROM visits v JOIN stores s ON s.code=v.store_code "
        f"WHERE {where} AND s.active=1 {'AND s.rep_code=?' if rep else ''}", p + sp).fetchone()["c"]
    return {"visits": row["visits"], "stores": row["stores"], "companies": row["companies"],
            "assigned_stores": assigned, "visited_assigned": vis_in,
            "rate": round(vis_in / assigned, 4) if assigned else 0.0}


def company_breakdown(conn, start: date, end: date, rep: str | None = None) -> list[dict]:
    where, p = "v.visit_date BETWEEN ? AND ?", [start.isoformat(), end.isoformat()]
    if rep:
        where += " AND v.rep_code=?"
        p.append(rep)
    rows = {r["company"]: dict(r) for r in conn.execute(
        f"SELECT s.company, COUNT(DISTINCT v.store_code) visited_stores, COUNT(*) visits "
        f"FROM visits v JOIN stores s ON s.code=v.store_code WHERE {where} GROUP BY s.company", p)}
    sw, sp = ("AND rep_code=?", [rep]) if rep else ("", [])
    totals = {r["company"]: r["c"] for r in conn.execute(
        f"SELECT company, COUNT(*) c FROM stores WHERE active=1 {sw} GROUP BY company", sp)}
    out = []
    for c in set(rows) | set(totals):
        r = rows.get(c, {"visited_stores": 0, "visits": 0})
        out.append({"company": c, "visited_stores": r["visited_stores"], "visits": r["visits"],
                    "assigned_stores": totals.get(c, 0)})
    return sorted(out, key=lambda x: (-x["visits"], -x["assigned_stores"], x["company"]))


def monthly(conn, ym: str, rep: str | None = None) -> dict:
    s, e = month_range(ym)
    trend = []
    for i in range(11, -1, -1):
        m = add_months(ym, -i)
        ms, me = month_range(m)
        t = summarize(conn, ms, me, rep)
        trend.append({"month": m, "stores": t["stores"], "companies": t["companies"], "visits": t["visits"]})
    return {"month": ym, "rep": rep, "summary": summarize(conn, s, e, rep),
            "companies": company_breakdown(conn, s, e, rep), "trend": trend}


def by_rep(conn, start: date, end: date) -> dict:
    rows = []
    for r in conn.execute("SELECT code, name FROM sales_reps WHERE active=1 ORDER BY code"):
        rows.append({"rep_code": r["code"], "rep_name": r["name"], **summarize(conn, start, end, r["code"])})
    return {"start": start.isoformat(), "end": end.isoformat(), "reps": rows,
            "total": summarize(conn, start, end, None)}


def rep_detail(conn, start: date, end: date, rep: str) -> dict:
    visits = [dict(r) for r in conn.execute(
        "SELECT v.id, v.visit_date, v.store_code, s.company, s.name store_name, v.memo "
        "FROM visits v JOIN stores s ON s.code=v.store_code "
        "WHERE v.rep_code=? AND v.visit_date BETWEEN ? AND ? ORDER BY v.visit_date DESC, v.id DESC",
        (rep, start.isoformat(), end.isoformat()))]
    return {"visits": visits, "companies": company_breakdown(conn, start, end, rep),
            "summary": summarize(conn, start, end, rep)}


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "").lower()


def store_list(conn, today: date, q: str = "", rep: str | None = None, company: str | None = None,
               min_days: int | None = None, unvisited: bool = False, sort: str = "days",
               order: str = "desc", mine_rep: str | None = None, limit: int | None = None) -> list[dict]:
    rows = conn.execute(
        "SELECT s.code, s.company, s.name, s.rep_code, r.name rep_name, "
        "MAX(v.visit_date) last_visit, COUNT(v.id) visit_count "
        "FROM stores s LEFT JOIN sales_reps r ON r.code=s.rep_code "
        "LEFT JOIN visits v ON v.store_code=s.code WHERE s.active=1 GROUP BY s.code").fetchall()
    fq = _fold(q).strip()
    out = []
    for r in rows:
        d = dict(r)
        if rep and d["rep_code"] != rep:
            continue
        if company and d["company"] != company:
            continue
        if fq and fq not in _fold(d["code"] + " " + d["company"] + " " + d["name"]):
            continue
        d["display_name"] = d["name"] or d["company"]
        if d["last_visit"]:
            d["days"] = (today - date.fromisoformat(d["last_visit"])).days
        else:
            d["days"] = None
        if unvisited and d["days"] is not None:
            continue
        if min_days is not None and (d["days"] is not None and d["days"] < min_days):
            continue  # 未訪問は「N日以上」にも含める(最も長く行っていない店舗のため)
        out.append(d)
    rev = order == "desc"
    if sort == "last_visit":   # 未訪問は最も古い扱い(昇順で先頭、降順で末尾)
        out.sort(key=lambda x: (x["last_visit"] or "", x["code"]), reverse=rev)
    elif sort == "company":
        out.sort(key=lambda x: (x["company"], x["name"], x["code"]), reverse=rev)
    else:  # days: 未訪問を最大扱い
        out.sort(key=lambda x: (x["days"] is None, x["days"] or 0, x["code"]), reverse=rev)
    if mine_rep:
        out.sort(key=lambda x: x["rep_code"] != mine_rep)  # 安定ソート: 担当店舗を先頭へ
    return out[:limit] if limit else out
