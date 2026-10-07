"""担当店舗マスタ(xlsx)の取り込みと検査レポート。

方針: 自動統合・自動削除はしない。問題はレポートに出して人が判断する。
"""
import json
import re
import unicodedata
from collections import Counter, defaultdict

import openpyxl

from . import auth, config

COLS = {"rep_code": "営業コード", "rep_name": "営業担当者", "code": "得意先コード",
        "company": "得意先名", "name": "店舗名"}


class ImportError_(Exception):
    pass


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def norm_code(v) -> tuple[str, bool]:
    """得意先コードを文字列で返す。(コード, 0埋めしたか)"""
    s = unicodedata.normalize("NFKC", _s(v))
    if s.isdigit() and len(s) < 5:
        return s.zfill(5), True
    return s, False


def read_rows(source) -> list[dict]:
    try:
        wb = openpyxl.load_workbook(source, read_only=True, data_only=True)
    except Exception as e:  # noqa: BLE001
        raise ImportError_(f"Excelファイルを開けませんでした: {e}") from e
    ws = wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    header = next(it, None)
    if not header:
        raise ImportError_("シートが空です")
    idx = {}
    for key, label in COLS.items():
        for i, h in enumerate(header):
            if _s(h) == label:
                idx[key] = i
        if key not in idx:
            raise ImportError_(f"列「{label}」が見つかりません")
    rows = []
    for n, r in enumerate(it, start=2):
        if r is None or all(c is None or _s(c) == "" for c in r):
            continue
        rows.append({"row": n, **{k: r[i] if i < len(r) else None for k, i in idx.items()}})
    return rows


def import_master(conn, source, filename: str, imported_by: str) -> dict:
    rows = read_rows(source)
    report = {"filename": filename, "total_rows": len(rows), "errors": [], "duplicates": [],
              "warnings": [], "blank_store_names": 0, "padded_codes": 0,
              "new_stores": 0, "updated_stores": 0, "unchanged_stores": 0,
              "deactivated_stores": 0, "reactivated_stores": 0, "new_users": [], "new_reps": 0}
    seen: dict[str, dict] = {}
    rep_names: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        code, padded = norm_code(r["code"])
        rep_code, rep_name = _s(r["rep_code"]), _s(r["rep_name"])
        company, name = _s(r["company"]), _s(r["name"])
        if not code or not rep_code or not company:
            report["errors"].append({"row": r["row"], "message": "得意先コード・営業コード・得意先名のいずれかが空欄のため取り込みませんでした"})
            continue
        if padded:
            report["padded_codes"] += 1
        if rep_code and rep_name:
            rep_names[rep_code][rep_name] += 1
        if code in seen:
            first = seen[code]
            report["duplicates"].append({"code": code, "kept_row": first["row"], "skipped_row": r["row"],
                                         "kept": f'{first["company"]} {first["name"]}'.strip(),
                                         "skipped": f"{company} {name}".strip()})
            continue
        if not name:
            report["blank_store_names"] += 1
        seen[code] = {"row": r["row"], "code": code, "company": company, "name": name, "rep_code": rep_code}
    for rc, c in rep_names.items():
        if len(c) > 1:
            report["warnings"].append(f"営業コード {rc} に複数の氏名があります: {', '.join(c)}(最多の氏名を採用)")

    with conn:
        # 営業
        for rc, c in rep_names.items():
            nm = c.most_common(1)[0][0]
            ex = conn.execute("SELECT 1 FROM sales_reps WHERE code=?", (rc,)).fetchone()
            if ex:
                conn.execute("UPDATE sales_reps SET name=?, active=1 WHERE code=?", (nm, rc))
            else:
                conn.execute("INSERT INTO sales_reps(code,name) VALUES(?,?)", (rc, nm))
                report["new_reps"] += 1
        # 営業ごとの初期ユーザー
        for rc, c in rep_names.items():
            if not conn.execute("SELECT 1 FROM users WHERE id=?", (rc,)).fetchone():
                pw = auth.temp_password()
                conn.execute("INSERT INTO users(id,rep_code,password_hash,role,must_change) VALUES(?,?,?,?,1)",
                             (rc, rc, auth.hash_password(pw), "sales"))
                report["new_users"].append({"id": rc, "name": c.most_common(1)[0][0], "temp_password": pw})
        # 店舗
        existing = {r["code"]: r for r in conn.execute("SELECT * FROM stores")}
        for code, s in seen.items():
            ex = existing.get(code)
            if not ex:
                conn.execute("INSERT INTO stores(code,company,name,rep_code) VALUES(?,?,?,?)",
                             (code, s["company"], s["name"], s["rep_code"]))
                report["new_stores"] += 1
            else:
                same = (ex["company"], ex["name"], ex["rep_code"], ex["active"]) == (s["company"], s["name"], s["rep_code"], 1)
                if same:
                    report["unchanged_stores"] += 1
                else:
                    if not ex["active"]:
                        report["reactivated_stores"] += 1
                    conn.execute("UPDATE stores SET company=?, name=?, rep_code=?, active=1 WHERE code=?",
                                 (s["company"], s["name"], s["rep_code"], code))
                    report["updated_stores"] += 1
        for code, ex in existing.items():
            if code not in seen and ex["active"]:
                conn.execute("UPDATE stores SET active=0 WHERE code=?", (code,))
                report["deactivated_stores"] += 1
        safe = {k: v for k, v in report.items() if k != "new_users"}
        safe["new_user_ids"] = [u["id"] for u in report["new_users"]]
        conn.execute("INSERT INTO import_log(imported_at,imported_by,filename,report_json) VALUES(?,?,?,?)",
                     (config.now_jst().isoformat(timespec="seconds"), imported_by, filename,
                      json.dumps(safe, ensure_ascii=False)))
    return report


# ---- 取引先名の候補一覧(表記ゆれの確認用。統合はしない) ----
_CORP = re.compile(r"\((株|有|合|資)\)|株式会社|有限会社|合同会社")


def company_key(name: str) -> str:
    s = unicodedata.normalize("NFKC", name).lower()
    s = _CORP.sub("", s)
    return re.sub(r"[\s・･\-]", "", s)


def name_candidates(conn) -> list[dict]:
    counts: Counter = Counter()
    for r in conn.execute("SELECT company FROM stores WHERE active=1"):
        counts[r["company"]] += 1
    names = list(counts)
    keys = {n: company_key(n) for n in names}
    parent = {n: n for n in names}
    reason: dict[str, set] = defaultdict(set)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b, why):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
            reason[rb] |= reason.pop(ra, set())
        reason[find(b)].add(why)

    by_key = defaultdict(list)
    for n in names:
        by_key[keys[n]].append(n)
    for ns in by_key.values():
        for a in ns[1:]:
            union(a, ns[0], "(株)などの位置・全角半角の違い")
    for a in names:
        for b in names:
            ka, kb = keys[a], keys[b]
            if ka != kb and len(ka) >= 3 and kb.startswith(ka):
                union(a, b, "前方一致(別名の可能性)")
    groups = defaultdict(list)
    for n in names:
        groups[find(n)].append(n)
    out = []
    for root, ns in groups.items():
        if len(ns) > 1:
            out.append({"reason": " / ".join(sorted(reason[root])),
                        "names": [{"name": n, "stores": counts[n]} for n in sorted(ns)]})
    return sorted(out, key=lambda g: g["names"][0]["name"])
