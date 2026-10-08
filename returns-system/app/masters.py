"""マスタの自動蓄積:入力された名前から既存を探し、なければ新規登録する。"""
from .db import now_iso
from .normalize import clean_display, norm_key, part_key

SIMPLE_TABLES = {
    "maker": "makers",
    "customer": "customers",
    "defect": "defect_types",
    "staff": "staff",
}


def _alias_target(conn, kind: str, key: str):
    row = conn.execute(
        "SELECT target_id FROM master_aliases WHERE kind=? AND alias_key=?", (kind, key)
    ).fetchone()
    return row["target_id"] if row else None


def resolve_simple(conn, kind: str, text: str | None) -> int | None:
    """名前→ID。無ければ「未整理の候補」として新規登録。空欄は None。"""
    name = clean_display(text)
    if not name:
        return None
    table = SIMPLE_TABLES[kind]
    key = norm_key(name)
    ts = now_iso()
    target = _alias_target(conn, kind, key)
    if target:
        row = conn.execute(f"SELECT id FROM {table} WHERE id=?", (target,)).fetchone()
    else:
        row = conn.execute(f"SELECT id FROM {table} WHERE name_key=?", (key,)).fetchone()
    if row:
        conn.execute(
            f"UPDATE {table} SET use_count=use_count+1, last_used_at=?, is_active=1, updated_at=? WHERE id=?",
            (ts, ts, row["id"]),
        )
        return row["id"]
    cur = conn.execute(
        f"INSERT INTO {table}(name,name_key,use_count,last_used_at,created_at,updated_at)"
        " VALUES(?,?,1,?,?,?)",
        (name, key, ts, ts, ts),
    )
    return cur.lastrowid


def resolve_product(conn, part_no: str, name: str | None, maker_id: int | None):
    """品番→(商品ID, 警告リスト)。品番単位でマスタ化し、商品名・メーカーは空なら補完する。"""
    display = clean_display(part_no).upper()  # 品番は大文字で統一表示
    key = part_key(display)
    if not key:
        raise ValueError("品番を入力してください")
    name = clean_display(name)
    ts = now_iso()
    warnings = []
    target = _alias_target(conn, "product", key)
    if target:
        row = conn.execute("SELECT * FROM products WHERE id=?", (target,)).fetchone()
    else:
        row = conn.execute("SELECT * FROM products WHERE part_no_key=?", (key,)).fetchone()
    if row is None:
        cur = conn.execute(
            "INSERT INTO products(part_no,part_no_key,name,name_key,maker_id,use_count,last_used_at,"
            "created_at,updated_at) VALUES(?,?,?,?,?,1,?,?,?)",
            (display, key, name, norm_key(name), maker_id, ts, ts, ts),
        )
        return cur.lastrowid, warnings
    sets, args = ["use_count=use_count+1", "last_used_at=?", "updated_at=?", "is_active=1"], [ts, ts]
    if name:
        if not row["name"]:
            sets += ["name=?", "name_key=?"]
            args += [name, norm_key(name)]
        elif norm_key(name) != row["name_key"]:
            warnings.append(
                f"品番「{row['part_no']}」は以前「{row['name']}」で登録されています(今回の入力:「{name}」)"
            )
            sets += ["name_conflict=1", "is_reviewed=0"]
    if maker_id and not row["maker_id"]:
        sets.append("maker_id=?")
        args.append(maker_id)
    conn.execute(f"UPDATE products SET {', '.join(sets)} WHERE id=?", (*args, row["id"]))
    return row["id"], warnings


def _like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def suggest(conn, kind: str, q: str, limit: int = 8) -> list[dict]:
    """入力途中の文字から候補を返す(全角半角・大小文字を問わない)。"""
    if kind == "product":
        k1, k2 = part_key(q), norm_key(q)
        rows = conn.execute(
            """SELECT p.id, p.part_no, p.name, m.name AS maker, p.name_conflict FROM products p
               LEFT JOIN makers m ON m.id=p.maker_id
               WHERE p.is_active=1 AND (?1='' OR p.part_no_key LIKE ?2 ESCAPE '\\' OR p.name_key LIKE ?3 ESCAPE '\\')
               ORDER BY CASE WHEN p.part_no_key LIKE ?4 ESCAPE '\\' THEN 0 ELSE 1 END,
                        p.use_count DESC, p.last_used_at DESC, p.part_no LIMIT ?5""",
            (k1 or k2, f"%{_like(k1)}%", f"%{_like(k2)}%", f"{_like(k1)}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]
    table = SIMPLE_TABLES[kind]
    k = norm_key(q)
    order = "sort_order, " if kind == "defect" and not k else ""
    rows = conn.execute(
        f"""SELECT id, name FROM {table} WHERE is_active=1 AND (?1='' OR name_key LIKE ?2 ESCAPE '\\')
            ORDER BY CASE WHEN name_key LIKE ?3 ESCAPE '\\' THEN 0 ELSE 1 END,
                     {order}use_count DESC, last_used_at DESC, name LIMIT ?4""",
        (k, f"%{_like(k)}%", f"{_like(k)}%", limit),
    ).fetchall()
    return [dict(r) for r in rows]


def find_product(conn, part_no: str):
    key = part_key(part_no)
    if not key:
        return None
    target = _alias_target(conn, "product", key)
    row = conn.execute(
        "SELECT p.id, p.part_no, p.name, m.name AS maker FROM products p LEFT JOIN makers m ON m.id=p.maker_id"
        " WHERE p.is_active=1 AND " + ("p.id=?" if target else "p.part_no_key=?"),
        (target or key,),
    ).fetchone()
    return dict(row) if row else None
