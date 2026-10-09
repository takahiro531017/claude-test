import csv
import io
from datetime import date, datetime

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import auth, config, db, importer, stats

STATIC = config.BASE_DIR / "app" / "static"
COOKIE = "vm_session"


# ---------- 起動時 ----------
def bootstrap() -> str | None:
    """DB初期化。管理者が居なければ作成し、一時パスワードを返す。"""
    conn = db.connect()
    try:
        db.init_db(conn)
        if not conn.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
            pw = auth.temp_password()
            conn.execute("INSERT OR REPLACE INTO users(id,rep_code,password_hash,role,must_change) VALUES('admin',NULL,?, 'admin',1)",
                         (auth.hash_password(pw),))
            conn.commit()
            return pw
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(_app):
    pw = bootstrap()
    if pw:
        print("=" * 60)
        print("管理者アカウントを作成しました(初回ログイン時にパスワード変更が必要です)")
        print(f"  ID: admin   一時パスワード: {pw}")
        print("=" * 60)
    yield


app = FastAPI(title="営業訪問管理", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


# ---------- 共通 ----------
def get_conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def _user(request: Request, conn=Depends(get_conn)):
    u = auth.user_for_token(conn, request.cookies.get(COOKIE))
    if not u:
        raise HTTPException(401, "ログインしてください")
    return u


def user_ok(u=Depends(_user)):
    if u["must_change"]:
        raise HTTPException(403, detail={"code": "must_change", "message": "パスワードを変更してください"})
    return u


def admin_ok(u=Depends(user_ok)):
    if u["role"] != "admin":
        raise HTTPException(403, "管理者のみ実行できます")
    return u


@app.middleware("http")
async def headers(request: Request, call_next):
    resp = await call_next(request)
    # 外部への読み込み・送信をブラウザ側でも禁止する
    resp.headers["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


def parse_date(s: str, name="日付") -> date:
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        raise HTTPException(400, f"{name}の形式が正しくありません")


def parse_month(s: str) -> str:
    try:
        datetime.strptime(s, "%Y-%m")
    except (ValueError, TypeError):
        raise HTTPException(400, "月の形式が正しくありません(YYYY-MM)")
    return s


def public_user(u, conn):
    rep = conn.execute("SELECT name FROM sales_reps WHERE code=?", (u["rep_code"],)).fetchone() if u["rep_code"] else None
    return {"id": u["id"], "role": u["role"], "rep_code": u["rep_code"],
            "name": rep["name"] if rep else "管理者", "must_change": bool(u["must_change"])}


# ---------- 認証 ----------
class LoginIn(BaseModel):
    id: str = Field(max_length=64)
    password: str = Field(max_length=200)


class PwIn(BaseModel):
    old_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


@app.post("/api/auth/login")
def login(body: LoginIn, request: Request, response: Response, conn=Depends(get_conn)):
    key = f"{body.id}|{request.client.host if request.client else ''}"
    if auth.is_locked(key):
        raise HTTPException(429, "試行回数が多すぎます。5分後にやり直してください")
    u = conn.execute("SELECT * FROM users WHERE id=? AND active=1", (body.id.strip(),)).fetchone()
    ok = auth.verify_password(u["password_hash"], body.password) if u else False
    if not ok:
        auth.record_fail(key)
        raise HTTPException(401, "IDまたはパスワードが違います")
    auth.clear_fails(key)
    token = auth.create_session(conn, u["id"])
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=config.SECURE_COOKIE,
                        max_age=config.SESSION_DAYS * 86400, path="/")
    return public_user(u, conn)


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, conn=Depends(get_conn)):
    auth.drop_session(conn, request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(u=Depends(_user), conn=Depends(get_conn)):
    return public_user(u, conn)


@app.post("/api/auth/change-password")
def change_password(body: PwIn, response: Response, u=Depends(_user), conn=Depends(get_conn)):
    if not auth.verify_password(u["password_hash"], body.old_password):
        raise HTTPException(400, "現在のパスワードが違います")
    if body.old_password == body.new_password:
        raise HTTPException(400, "現在と同じパスワードは使えません")
    err = auth.validate_new_password(u["id"], body.new_password)
    if err:
        raise HTTPException(400, err)
    conn.execute("UPDATE users SET password_hash=?, must_change=0 WHERE id=?",
                 (auth.hash_password(body.new_password), u["id"]))
    conn.commit()
    # 他の端末のセッションは破棄し、新しいセッションに切り替える
    auth.drop_session(conn, None, u["id"])
    token = auth.create_session(conn, u["id"])
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=config.SECURE_COOKIE,
                        max_age=config.SESSION_DAYS * 86400, path="/")
    return {"ok": True}


# ---------- メタ / 設定 ----------
@app.get("/api/meta")
def meta(u=Depends(user_ok), conn=Depends(get_conn)):
    reps = [dict(r) for r in conn.execute("SELECT code, name FROM sales_reps WHERE active=1 ORDER BY code")]
    companies = [r["company"] for r in conn.execute(
        "SELECT DISTINCT company FROM stores WHERE active=1 AND manual=0 ORDER BY company")]
    return {"user": public_user(u, conn), "reps": reps, "companies": companies,
            "today": config.today_jst().isoformat(),
            "threshold_days": int(db.get_setting(conn, "threshold_days", str(config.DEFAULT_THRESHOLD_DAYS)))}


class SettingsIn(BaseModel):
    threshold_days: int = Field(ge=1, le=3650)


@app.put("/api/admin/settings")
def put_settings(body: SettingsIn, u=Depends(admin_ok), conn=Depends(get_conn)):
    conn.execute("INSERT OR REPLACE INTO settings VALUES('threshold_days',?)", (str(body.threshold_days),))
    conn.commit()
    return {"threshold_days": body.threshold_days}


# ---------- 店舗 ----------
@app.get("/api/stores")
def stores(q: str = "", rep: str | None = None, company: str | None = None, min_days: int | None = None,
           unvisited: bool = False, sort: str = "days", order: str = "desc", mine_first: bool = False,
           limit: int | None = None, company_q: str = "", u=Depends(user_ok), conn=Depends(get_conn)):
    items = stats.store_list(conn, config.today_jst(), q, rep or None, company or None, min_days, unvisited,
                             sort, order, u["rep_code"] if mine_first else None, limit, company_q)
    return {"items": items, "count": len(items)}


@app.get("/api/stores/{code}")
def store_detail(code: str, u=Depends(user_ok), conn=Depends(get_conn)):
    s = conn.execute("SELECT s.*, r.name rep_name FROM stores s LEFT JOIN sales_reps r ON r.code=s.rep_code WHERE s.code=?",
                     (code,)).fetchone()
    if not s:
        raise HTTPException(404, "店舗が見つかりません")
    visits = [dict(r) for r in conn.execute(
        "SELECT v.id, v.visit_date, v.rep_code, r.name rep_name, v.memo FROM visits v "
        "LEFT JOIN sales_reps r ON r.code=v.rep_code WHERE v.store_code=? ORDER BY v.visit_date DESC, v.id DESC", (code,))]
    d = dict(s)
    d["display_name"] = d["name"] or d["company"]
    d["last_visit"] = visits[0]["visit_date"] if visits else None
    d["days"] = (config.today_jst() - date.fromisoformat(d["last_visit"])).days if d["last_visit"] else None
    return {"store": d, "visits": visits}


# ---------- 訪問 ----------
class VisitIn(BaseModel):
    visit_date: str
    store_code: str = ""
    manual_company: str = Field(default="", max_length=60)   # リスト外の訪問先を手入力するとき
    manual_name: str = Field(default="", max_length=60)
    rep_code: str | None = None
    memo: str = Field(default="", max_length=1000)
    force: bool = False


def _manual_store(conn, rep: str, company: str, name: str) -> str:
    """リスト外の訪問先。同じ法人名+訪問先名があれば再利用し、なければ M0001 形式のコードで作る。"""
    company, name = (company.strip() or "(リスト外)"), name.strip()
    row = conn.execute("SELECT code FROM stores WHERE manual=1 AND company=? AND name=?", (company, name)).fetchone()
    if row:
        return row["code"]
    n = conn.execute("SELECT COUNT(*) c FROM stores WHERE manual=1").fetchone()["c"] + 1
    while conn.execute("SELECT 1 FROM stores WHERE code=?", (f"M{n:04d}",)).fetchone():
        n += 1
    code = f"M{n:04d}"
    conn.execute("INSERT INTO stores(code,company,name,rep_code,active,manual) VALUES(?,?,?,?,1,1)", (code, company, name, rep))
    return code


def _can_edit(u, v) -> bool:
    return u["role"] == "admin" or (u["rep_code"] is not None and u["rep_code"] == v["rep_code"])


def _check_visit(conn, u, body: VisitIn, exclude_id: int | None = None) -> tuple[str, str]:
    d = parse_date(body.visit_date, "訪問日")
    rep = body.rep_code or u["rep_code"]
    if not rep or not conn.execute("SELECT 1 FROM sales_reps WHERE code=?", (rep,)).fetchone():
        raise HTTPException(400, "営業担当者を選んでください")
    if u["role"] != "admin" and rep != u["rep_code"]:
        raise HTTPException(403, "自分の訪問のみ登録できます")
    if body.manual_name.strip():
        body.store_code = _manual_store(conn, rep, body.manual_company, body.manual_name)
    if not conn.execute("SELECT 1 FROM stores WHERE code=?", (body.store_code,)).fetchone():
        raise HTTPException(400, "店舗を選ぶか、訪問先名を入力してください")
    if not body.force:
        if d > config.today_jst():
            raise HTTPException(409, detail={"code": "future", "message": "未来の日付です。このまま登録しますか?"})
        dup = conn.execute("SELECT id FROM visits WHERE visit_date=? AND store_code=? AND rep_code=? AND id IS NOT ?",
                           (d.isoformat(), body.store_code, rep, exclude_id)).fetchone()
        if dup:
            raise HTTPException(409, detail={"code": "duplicate",
                                             "message": "同じ日に同じ営業が同じ店舗を登録済みです。もう1件登録しますか?"})
    return d.isoformat(), rep


@app.post("/api/visits", status_code=201)
def create_visit(body: VisitIn, u=Depends(user_ok), conn=Depends(get_conn)):
    d, rep = _check_visit(conn, u, body)
    now = config.now_jst().isoformat(timespec="seconds")
    cur = conn.execute("INSERT INTO visits(visit_date,store_code,rep_code,memo,created_by,created_at,updated_at) "
                       "VALUES(?,?,?,?,?,?,?)", (d, body.store_code, rep, body.memo.strip(), u["id"], now, now))
    conn.commit()
    return {"id": cur.lastrowid}


@app.put("/api/visits/{vid}")
def update_visit(vid: int, body: VisitIn, u=Depends(user_ok), conn=Depends(get_conn)):
    v = conn.execute("SELECT * FROM visits WHERE id=?", (vid,)).fetchone()
    if not v:
        raise HTTPException(404, "訪問が見つかりません")
    if not _can_edit(u, v):
        raise HTTPException(403, "本人または管理者のみ編集できます")
    if not body.rep_code:
        body.rep_code = v["rep_code"]
    d, rep = _check_visit(conn, u, body, exclude_id=vid)
    conn.execute("UPDATE visits SET visit_date=?, store_code=?, rep_code=?, memo=?, updated_at=? WHERE id=?",
                 (d, body.store_code, rep, body.memo.strip(), config.now_jst().isoformat(timespec="seconds"), vid))
    conn.commit()
    return {"id": vid}


@app.delete("/api/visits/{vid}")
def delete_visit(vid: int, u=Depends(user_ok), conn=Depends(get_conn)):
    v = conn.execute("SELECT * FROM visits WHERE id=?", (vid,)).fetchone()
    if not v:
        raise HTTPException(404, "訪問が見つかりません")
    if not _can_edit(u, v):
        raise HTTPException(403, "本人または管理者のみ削除できます")
    conn.execute("DELETE FROM visits WHERE id=?", (vid,))
    conn.commit()
    return {"ok": True}


@app.get("/api/visits")
def list_visits(rep: str | None = None, start: str | None = None, end: str | None = None, limit: int = 50,
                u=Depends(user_ok), conn=Depends(get_conn)):
    w, p = [], []
    if rep:
        w.append("v.rep_code=?"); p.append(rep)
    if start:
        w.append("v.visit_date>=?"); p.append(parse_date(start).isoformat())
    if end:
        w.append("v.visit_date<=?"); p.append(parse_date(end).isoformat())
    sql = ("SELECT v.id, v.visit_date, v.store_code, s.company, s.name store_name, s.manual, v.rep_code, r.name rep_name, v.memo "
           "FROM visits v JOIN stores s ON s.code=v.store_code LEFT JOIN sales_reps r ON r.code=v.rep_code "
           + ("WHERE " + " AND ".join(w) if w else "") + " ORDER BY v.visit_date DESC, v.id DESC LIMIT ?")
    items = [dict(r) for r in conn.execute(sql, p + [min(max(limit, 1), 500)])]
    for it in items:
        it["display_name"] = it["store_name"] or it["company"]
        it["editable"] = u["role"] == "admin" or u["rep_code"] == it["rep_code"]
    return {"items": items}


# ---------- 集計 ----------
@app.get("/api/stats/monthly")
def stats_monthly(month: str | None = None, rep: str | None = None, u=Depends(user_ok), conn=Depends(get_conn)):
    ym = parse_month(month or config.today_jst().strftime("%Y-%m"))
    return stats.monthly(conn, ym, rep or None)


def _period(month, start, end):
    if month:
        return stats.month_range(parse_month(month))
    if not (start and end):
        raise HTTPException(400, "月、または開始日と終了日を指定してください")
    s, e = parse_date(start, "開始日"), parse_date(end, "終了日")
    if s > e:
        raise HTTPException(400, "開始日は終了日以前にしてください")
    return s, e


@app.get("/api/stats/by-rep")
def stats_by_rep(month: str | None = None, start: str | None = None, end: str | None = None,
                 u=Depends(user_ok), conn=Depends(get_conn)):
    s, e = _period(month, start, end)
    return stats.by_rep(conn, s, e)


@app.get("/api/stats/by-rep/csv")
def stats_by_rep_csv(month: str | None = None, start: str | None = None, end: str | None = None,
                     u=Depends(admin_ok), conn=Depends(get_conn)):
    s, e = _period(month, start, end)
    data = stats.by_rep(conn, s, e)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["営業コード", "営業担当者", "訪問回数", "訪問した店舗数", "担当店舗数", "訪問率(%)"])
    for r in data["reps"]:
        w.writerow([_csv_safe(r["rep_code"]), _csv_safe(r["rep_name"]), r["visits"], r["stores"],
                    r["assigned_stores"], round(r["rate"] * 100, 1)])
    body = "﻿" + buf.getvalue()  # Excelで文字化けしないようBOM付きUTF-8
    return StreamingResponse(iter([body]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="by_rep_{s}_{e}.csv"'})


def _csv_safe(v: str) -> str:
    return "'" + v if v[:1] in "=+-@" else v  # CSVインジェクション対策


@app.get("/api/stats/rep/{rep}")
def stats_rep(rep: str, month: str | None = None, start: str | None = None, end: str | None = None,
              u=Depends(user_ok), conn=Depends(get_conn)):
    s, e = _period(month, start, end)
    return stats.rep_detail(conn, s, e, rep)


@app.get("/api/reps/{rep}/stores")
def rep_stores(rep: str, month: str | None = None, start: str | None = None, end: str | None = None,
               u=Depends(user_ok), conn=Depends(get_conn)):
    r = conn.execute("SELECT code, name FROM sales_reps WHERE code=?", (rep,)).fetchone()
    if not r:
        raise HTTPException(404, "営業が見つかりません")
    s, e = _period(month, start, end)
    d = stats.rep_stores(conn, s, e, rep, config.today_jst())
    d["rep"] = dict(r)
    d["start"], d["end"] = s.isoformat(), e.isoformat()
    return d


# ---------- 管理 ----------
@app.post("/api/admin/import")
def admin_import(file: UploadFile = File(...), u=Depends(admin_ok), conn=Depends(get_conn)):
    raw = file.file.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, "ファイルが大きすぎます")
    try:
        return importer.import_master(conn, io.BytesIO(raw), file.filename or "master.xlsx", u["id"])
    except importer.ImportError_ as e:
        raise HTTPException(400, str(e))


@app.get("/api/admin/import-log")
def import_log(u=Depends(admin_ok), conn=Depends(get_conn)):
    import json
    return {"items": [{"id": r["id"], "imported_at": r["imported_at"], "imported_by": r["imported_by"],
                       "filename": r["filename"], "report": json.loads(r["report_json"])}
                      for r in conn.execute("SELECT * FROM import_log ORDER BY id DESC LIMIT 20")]}


@app.get("/api/admin/name-candidates")
def name_candidates(u=Depends(admin_ok), conn=Depends(get_conn)):
    return {"groups": importer.name_candidates(conn)}


@app.get("/api/admin/users")
def admin_users(u=Depends(admin_ok), conn=Depends(get_conn)):
    return {"items": [dict(r) for r in conn.execute(
        "SELECT u.id, u.rep_code, r.name rep_name, u.role, u.must_change, u.active FROM users u "
        "LEFT JOIN sales_reps r ON r.code=u.rep_code ORDER BY u.role, u.id")]}


class UserPatch(BaseModel):
    role: str | None = None
    active: bool | None = None


@app.patch("/api/admin/users/{uid}")
def admin_user_patch(uid: str, body: UserPatch, u=Depends(admin_ok), conn=Depends(get_conn)):
    t = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not t:
        raise HTTPException(404, "ユーザーが見つかりません")
    if uid == u["id"] and (body.role == "sales" or body.active is False):
        raise HTTPException(400, "自分自身の権限は下げられません")
    if body.role is not None:
        if body.role not in ("sales", "admin"):
            raise HTTPException(400, "役割が正しくありません")
        conn.execute("UPDATE users SET role=? WHERE id=?", (body.role, uid))
    if body.active is not None:
        conn.execute("UPDATE users SET active=? WHERE id=?", (int(body.active), uid))
        if not body.active:
            auth.drop_session(conn, None, uid)
    conn.commit()
    return {"ok": True}


@app.post("/api/admin/users/{uid}/reset-password")
def admin_reset(uid: str, u=Depends(admin_ok), conn=Depends(get_conn)):
    if not conn.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone():
        raise HTTPException(404, "ユーザーが見つかりません")
    pw = auth.temp_password()
    conn.execute("UPDATE users SET password_hash=?, must_change=1 WHERE id=?", (auth.hash_password(pw), uid))
    conn.commit()
    auth.drop_session(conn, None, uid)
    return {"id": uid, "temp_password": pw}


# ---------- 静的ファイル(データを含まない画面の枠のみ) ----------
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/sw.js")
def sw():
    return FileResponse(STATIC / "sw.js", media_type="application/javascript", headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=STATIC), name="static")
