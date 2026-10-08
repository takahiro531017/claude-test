"""返品の登録・更新・状況管理・検索などの業務処理。"""
from datetime import date, datetime

from . import masters
from .db import get_setting, now_iso, tx
from .normalize import clean_display, norm_key, part_key

STATUSES = ["received", "checking", "decided", "done"]
STATUS_LABELS = {"received": "受付済", "checking": "確認中", "decided": "処分決定済", "done": "完了"}
DISPOSITIONS = ["recycle", "discard", "maker_return"]
DISPOSITION_LABELS = {"recycle": "リサイクル販売", "discard": "廃棄", "maker_return": "メーカー返品"}


class BusinessError(ValueError):
    """画面にそのまま表示できる日本語メッセージ付きのエラー。"""


def parse_date(s: str | None, default: date | None = None) -> date:
    if not s:
        return default or date.today()
    s = clean_display(s).replace("/", "-")
    try:
        return date.fromisoformat(s)
    except ValueError as e:
        raise BusinessError("日付の形式が正しくありません") from e


def next_receipt_no(conn, on: date) -> str:
    """受付番号を採番(RT-YYYYMMDD-NNN)。呼び出し側のトランザクション内で使う。"""
    key = on.strftime("%Y%m%d")
    seq = conn.execute(
        "INSERT INTO receipt_counters(date_key,last_seq) VALUES(?,1)"
        " ON CONFLICT(date_key) DO UPDATE SET last_seq=last_seq+1 RETURNING last_seq",
        (key,),
    ).fetchone()[0]
    return f"RT-{key}-{seq:03d}"


def _event(conn, return_id, actor, action, from_value=None, to_value=None, note=""):
    conn.execute(
        "INSERT INTO return_events(return_id,at,actor,action,from_value,to_value,note) VALUES(?,?,?,?,?,?,?)",
        (return_id, now_iso(), actor or "不明", action, from_value, to_value, note),
    )


def _int_qty(v) -> int:
    try:
        q = int(str(v).strip() or 1)
    except ValueError as e:
        raise BusinessError("数量は数字で入力してください") from e
    if q < 1:
        raise BusinessError("数量は1以上にしてください")
    return q


def _resolve_common(conn, d: dict):
    """入力値からマスタIDを解決する(自動蓄積)。"""
    if not clean_display(d.get("part_no")):
        raise BusinessError("品番を入力してください")
    defect_name = clean_display(d.get("defect"))
    if not defect_name:
        raise BusinessError("不良内容を選ぶか入力してください")
    maker_id = masters.resolve_simple(conn, "maker", d.get("maker"))
    product_id, warnings = masters.resolve_product(conn, d["part_no"], d.get("product_name"), maker_id)
    prod = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not maker_id:
        maker_id = prod["maker_id"]
    return {
        "customer_id": masters.resolve_simple(conn, "customer", d.get("customer")),
        "product_id": product_id,
        "part_no_text": prod["part_no"],
        "product_name_text": clean_display(d.get("product_name")) or prod["name"],
        "maker_id": maker_id,
        "defect_type_id": masters.resolve_simple(conn, "defect", defect_name),
        "serial_no": clean_display(d.get("serial_no")),
        "quantity": _int_qty(d.get("quantity")),
        "defect_text": (d.get("defect_text") or "").strip(),
        "reason_note": (d.get("reason_note") or "").strip(),
    }, warnings


def create_return(conn, d: dict, actor: str, today: date | None = None) -> dict:
    """返品を受付登録する。戻り値は {id, receipt_no, warnings}。"""
    received_on = parse_date(d.get("received_on"), today)
    ts = now_iso()
    with tx(conn):
        staff_id = masters.resolve_simple(conn, "staff", d.get("staff") or actor)
        f, warnings = _resolve_common(conn, d)
        receipt_no = next_receipt_no(conn, received_on)
        cur = conn.execute(
            """INSERT INTO returns(receipt_no,received_on,staff_id,customer_id,product_id,part_no_text,
               product_name_text,maker_id,serial_no,quantity,defect_type_id,defect_text,reason_note,
               status,status_changed_at,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'received',?,?,?)""",
            (receipt_no, received_on.isoformat(), staff_id, f["customer_id"], f["product_id"],
             f["part_no_text"], f["product_name_text"], f["maker_id"], f["serial_no"], f["quantity"],
             f["defect_type_id"], f["defect_text"], f["reason_note"], ts, ts, ts),
        )
        rid = cur.lastrowid
        _event(conn, rid, actor or d.get("staff"), "create", None, "received", "受付登録")
    return {"id": rid, "receipt_no": receipt_no, "warnings": warnings}


EDIT_LABELS = {
    "customer": "返品元", "part_no": "品番", "product_name": "商品名", "maker": "メーカー",
    "serial_no": "製造番号", "quantity": "数量", "defect": "不良内容", "defect_text": "不良の詳細",
    "reason_note": "備考",
}


def update_return(conn, rid: int, d: dict, actor: str) -> dict:
    """受付内容の修正・あとからの追記。変更点は履歴に残す。"""
    with tx(conn):
        old = get_return(conn, rid)
        if old is None:
            raise BusinessError("返品が見つかりません")
        f, warnings = _resolve_common(conn, d)
        received_on = parse_date(d.get("received_on"), date.fromisoformat(old["received_on"]))
        changes = []
        new_view = {
            "customer": masters_name(conn, "customers", f["customer_id"]),
            "part_no": f["part_no_text"], "product_name": f["product_name_text"],
            "maker": masters_name(conn, "makers", f["maker_id"]),
            "serial_no": f["serial_no"], "quantity": str(f["quantity"]),
            "defect": masters_name(conn, "defect_types", f["defect_type_id"]),
            "defect_text": f["defect_text"], "reason_note": f["reason_note"],
        }
        old_view = {
            "customer": old["customer_name"] or "", "part_no": old["part_no_text"],
            "product_name": old["product_name_text"], "maker": old["maker_name"] or "",
            "serial_no": old["serial_no"], "quantity": str(old["quantity"]),
            "defect": old["defect_name"] or "", "defect_text": old["defect_text"],
            "reason_note": old["reason_note"],
        }
        for k, label in EDIT_LABELS.items():
            if old_view[k] != new_view[k]:
                changes.append(f"{label}: {old_view[k] or '(空)'} → {new_view[k] or '(空)'}")
        conn.execute(
            """UPDATE returns SET received_on=?, customer_id=?, product_id=?, part_no_text=?,
               product_name_text=?, maker_id=?, serial_no=?, quantity=?, defect_type_id=?, defect_text=?,
               reason_note=?, updated_at=? WHERE id=?""",
            (received_on.isoformat(), f["customer_id"], f["product_id"], f["part_no_text"],
             f["product_name_text"], f["maker_id"], f["serial_no"], f["quantity"], f["defect_type_id"],
             f["defect_text"], f["reason_note"], now_iso(), rid),
        )
        if changes:
            _event(conn, rid, actor, "edit", None, None, " / ".join(changes))
    return {"warnings": warnings, "changed": bool(changes)}


def masters_name(conn, table: str, id_):
    if not id_:
        return ""
    row = conn.execute(f"SELECT name FROM {table} WHERE id=?", (id_,)).fetchone()
    return row["name"] if row else ""


_SELECT = """
SELECT r.*, c.name AS customer_name, m.name AS maker_name, d.name AS defect_name, s.name AS staff_name,
       COALESCE(NULLIF(r.product_name_text,''), p.name, '') AS product_name
FROM returns r
LEFT JOIN customers c ON c.id=r.customer_id
LEFT JOIN makers m ON m.id=r.maker_id
LEFT JOIN defect_types d ON d.id=r.defect_type_id
LEFT JOIN staff s ON s.id=r.staff_id
LEFT JOIN products p ON p.id=r.product_id
"""


def get_return(conn, rid: int):
    return conn.execute(_SELECT + " WHERE r.id=?", (rid,)).fetchone()


def find_by_receipt_no(conn, text: str, today: date | None = None):
    """受付番号の入力(全角・小文字・日付省略可)から返品を探す。"""
    t = clean_display(text).upper().replace(" ", "")
    if not t:
        return None
    if t.isdigit() and len(t) <= 3:  # 「5」→ 今日の005
        t = f"RT-{(today or date.today()).strftime('%Y%m%d')}-{int(t):03d}"
    elif not t.startswith("RT-"):
        t = "RT-" + t.lstrip("-")
    return conn.execute(_SELECT + " WHERE r.receipt_no=?", (t,)).fetchone()


def photos_of(conn, rid: int):
    return conn.execute("SELECT * FROM return_photos WHERE return_id=? ORDER BY id", (rid,)).fetchall()


def events_of(conn, rid: int):
    return conn.execute("SELECT * FROM return_events WHERE return_id=? ORDER BY id DESC", (rid,)).fetchall()


# ---- 状況管理 ------------------------------------------------------------

def set_disposition(conn, rid: int, disposition: str, actor: str):
    """処分方法を選ぶ。確認中・処分決定済のときだけ変更できる(修理不能→廃棄への変更もここ)。"""
    if disposition not in DISPOSITIONS:
        raise BusinessError("処分方法が正しくありません")
    with tx(conn):
        r = get_return(conn, rid)
        if r is None:
            raise BusinessError("返品が見つかりません")
        if r["status"] not in ("checking", "decided"):
            raise BusinessError("処分方法を選べるのは「確認中」「処分決定済」のときです")
        if r["disposition"] == disposition:
            return
        conn.execute("UPDATE returns SET disposition=?, updated_at=? WHERE id=?", (disposition, now_iso(), rid))
        _event(conn, rid, actor, "disposition", DISPOSITION_LABELS.get(r["disposition"], ""),
               DISPOSITION_LABELS[disposition])


def change_status(conn, rid: int, new_status: str, actor: str, note: str = ""):
    """状況を1段階進める、または1段階戻す。"""
    if new_status not in STATUSES:
        raise BusinessError("状況が正しくありません")
    with tx(conn):
        r = get_return(conn, rid)
        if r is None:
            raise BusinessError("返品が見つかりません")
        cur, new = STATUSES.index(r["status"]), STATUSES.index(new_status)
        if abs(new - cur) != 1:
            raise BusinessError("状況は1段階ずつ変更してください")
        if new > cur and new_status in ("decided", "done") and not r["disposition"]:
            raise BusinessError("先に処分方法を選んでください")
        ts = now_iso()
        closed = ts if new_status == "done" else None
        conn.execute(
            "UPDATE returns SET status=?, status_changed_at=?, closed_at=?, updated_at=? WHERE id=?",
            (new_status, ts, closed, ts, rid),
        )
        _event(conn, rid, actor, "status", STATUS_LABELS[r["status"]], STATUS_LABELS[new_status], note)


def mark_printed(conn, ids: list[int], actor: str):
    ts = now_iso()
    with tx(conn):
        for rid in ids:
            conn.execute(
                "UPDATE returns SET print_status='printed', printed_at=?, print_count=print_count+1 WHERE id=?",
                (ts, rid),
            )
            _event(conn, rid, actor, "print", None, None, "受付票を印刷")


# ---- 一覧・検索 ----------------------------------------------------------

def stale_days(r, today: date | None = None) -> int:
    end = datetime.fromisoformat(r["closed_at"]).date() if r["closed_at"] else (today or date.today())
    return (end - date.fromisoformat(r["received_on"])).days


def stale_level(conn, r, today: date | None = None) -> str:
    """'' / 'warn' / 'over'。完了済みは強調しない。"""
    if r["status"] == "done":
        return ""
    days = stale_days(r, today)
    if days >= int(get_setting(conn, "stale_days", "14")):
        return "over"
    if days >= int(get_setting(conn, "stale_warn_days", "7")):
        return "warn"
    return ""


def list_returns(conn, f: dict, limit: int = 100, offset: int = 0):
    where, args = [], []
    if f.get("status"):
        where.append("r.status=?"); args.append(f["status"])
    if f.get("open_only"):
        where.append("r.status!='done'")
    if f.get("disposition"):
        if f["disposition"] == "none":
            where.append("r.disposition IS NULL")
        else:
            where.append("r.disposition=?"); args.append(f["disposition"])
    if f.get("maker"):
        where.append("m.name_key LIKE ?"); args.append(f"%{norm_key(f['maker'])}%")
    if f.get("customer"):
        where.append("c.name_key LIKE ?"); args.append(f"%{norm_key(f['customer'])}%")
    if f.get("part_no"):
        where.append("p.part_no_key LIKE ?"); args.append(f"%{part_key(f['part_no'])}%")
    if f.get("date_from"):
        where.append("r.received_on>=?"); args.append(parse_date(f["date_from"]).isoformat())
    if f.get("date_to"):
        where.append("r.received_on<=?"); args.append(parse_date(f["date_to"]).isoformat())
    if f.get("unprinted"):
        where.append("r.print_status='unprinted'")
    if f.get("q"):
        k, pk = norm_key(f["q"]), part_key(f["q"])
        where.append("(upper(r.receipt_no) LIKE ? OR p.part_no_key LIKE ? OR r.product_name_text LIKE ?"
                     " OR upper(r.serial_no) LIKE ?)")
        args += [f"%{clean_display(f['q']).upper()}%", f"%{pk}%", f"%{clean_display(f['q'])}%",
                 f"%{clean_display(f['q']).upper()}%"]
    sql = _SELECT + (" WHERE " + " AND ".join(where) if where else "")
    total = conn.execute("SELECT COUNT(*) FROM (" + sql + ")", args).fetchone()[0]
    rows = conn.execute(sql + " ORDER BY r.received_on DESC, r.id DESC LIMIT ? OFFSET ?",
                        (*args, limit, offset)).fetchall()
    return rows, total


def status_summary(conn) -> dict:
    """ホーム・置き場の件数(未完了のみ)。"""
    out = {s: 0 for s in STATUSES[:3]}
    for row in conn.execute("SELECT status, COUNT(*) n FROM returns WHERE status!='done' GROUP BY status"):
        out[row["status"]] = row["n"]
    return out
