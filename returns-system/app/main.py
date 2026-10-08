"""Webアプリ本体(画面とAPI)。"""
import contextlib
from datetime import date
from urllib.parse import quote, unquote

import segno
from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import config, db, masters, photos, service, slip
from .db import get_setting
from .normalize import clean_display

STAFF_COOKIE = "staff_name"


@contextlib.asynccontextmanager
async def lifespan(app):
    conn = db.connect()
    db.init_db(conn)
    conn.close()
    yield


app = FastAPI(title="返品管理", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=config.BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=config.BASE_DIR / "templates")
templates.env.globals.update(
    STATUS_LABELS=service.STATUS_LABELS, DISPOSITION_LABELS=service.DISPOSITION_LABELS,
    STATUSES=service.STATUSES, DISPOSITIONS=service.DISPOSITIONS,
)
templates.env.filters["ymd"] = lambda s: (s or "")[:10].replace("-", "/")
templates.env.filters["ymdhm"] = lambda s: (s or "")[:16].replace("-", "/").replace("T", " ")


def get_conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def actor_of(request: Request) -> str:
    return unquote(request.cookies.get(STAFF_COOKIE, ""))


def render(request: Request, name: str, **ctx):
    ctx.setdefault("actor", actor_of(request))
    return templates.TemplateResponse(request, name, ctx)


def need_staff(request: Request):
    """担当者が未選択ならこの端末で選んでもらう(端末に記憶される)。"""
    if not actor_of(request):
        nxt = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse(f"/staff?next={quote(nxt)}", status_code=303)
    return None


def base_url(conn, request: Request) -> str:
    return (get_setting(conn, "base_url") or config.env_base_url() or str(request.base_url)).rstrip("/")


def slip_dict(r, url_base: str) -> dict:
    return {
        "receipt_no": r["receipt_no"], "received_on": r["received_on"], "customer": r["customer_name"] or "",
        "part_no": r["part_no_text"], "product_name": r["product_name"], "maker": r["maker_name"] or "",
        "serial_no": r["serial_no"], "defect": r["defect_name"] or "", "quantity": r["quantity"],
        "staff": r["staff_name"] or "", "url": f"{url_base}/r/{r['receipt_no']}",
    }


def qr_svg(url: str) -> str:
    return segno.make(url, error="m", micro=False).svg_inline(omitsize=True, border=2, dark="#000")


def redirect_detail(receipt_no: str, **q):
    qs = "&".join(f"{k}={quote(str(v))}" for k, v in q.items())
    return RedirectResponse(f"/r/{receipt_no}" + (f"?{qs}" if qs else ""), status_code=303)


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


@app.get("/fonts/ipaexg.ttf")
def font_file():
    """印刷用HTMLでもPDFと同じ書体で出すため、同梱のIPAexゴシックを配信する。"""
    return FileResponse(config.BASE_DIR / "fonts" / "ipaexg.ttf", media_type="font/ttf",
                        headers={"Cache-Control": "max-age=604800"})


# ---- 担当者 --------------------------------------------------------------

@app.get("/staff", response_class=HTMLResponse)
def staff_page(request: Request, next: str = "/", conn=Depends(get_conn)):
    return render(request, "staff.html", next=next, staff_list=masters.suggest(conn, "staff", "", 30))


@app.post("/staff")
def staff_select(request: Request, name: str = Form(""), pick: str = Form(""), next: str = Form("/"), conn=Depends(get_conn)):
    name = clean_display(pick or name)
    if not name:
        return RedirectResponse(f"/staff?next={quote(next)}", status_code=303)
    with db.tx(conn):
        masters.resolve_simple(conn, "staff", name)
    if not next.startswith("/") or next.startswith("//"):
        next = "/"
    resp = RedirectResponse(next, status_code=303)
    resp.set_cookie(STAFF_COOKIE, quote(name), max_age=60 * 60 * 24 * 365 * 5, samesite="lax")
    return resp


# ---- ホーム・検索 ----------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request, err: str = "", conn=Depends(get_conn)):
    if (r := need_staff(request)):
        return r
    today = date.today().isoformat()
    todays = service.list_returns(conn, {"date_from": today, "date_to": today}, 5)
    unprinted = conn.execute("SELECT COUNT(*) FROM returns WHERE print_status='unprinted'").fetchone()[0]
    return render(request, "home.html", summary=service.status_summary(conn), todays=todays,
                  unprinted=unprinted, err=err)


@app.get("/find")
def find(no: str = "", conn=Depends(get_conn)):
    r = service.find_by_receipt_no(conn, no)
    if r is None:
        return RedirectResponse(f"/?err={quote('その受付番号は見つかりませんでした')}", status_code=303)
    return RedirectResponse(f"/r/{r['receipt_no']}", status_code=303)


# ---- 受付登録 --------------------------------------------------------------

def _form_ctx(conn):
    return {"defects": masters.suggest(conn, "defect", "", 12), "today": date.today().isoformat()}


@app.get("/new", response_class=HTMLResponse)
def new_form(request: Request, conn=Depends(get_conn)):
    if (r := need_staff(request)):
        return r
    return render(request, "form.html", mode="new", ret=None, **_form_ctx(conn))


async def _save_photos(conn, rid, receipt_no, files):
    errs = 0
    for f in files or []:
        data = await f.read()
        if not data:
            continue
        try:
            with db.tx(conn):
                photos.save_photo(conn, rid, receipt_no, data)
        except photos.PhotoError:
            errs += 1
    return errs


@app.post("/api/returns")
async def api_create(request: Request, conn=Depends(get_conn),
                     customer: str = Form(""), part_no: str = Form(""), product_name: str = Form(""),
                     maker: str = Form(""), serial_no: str = Form(""), quantity: str = Form("1"),
                     defect: str = Form(""), defect_text: str = Form(""), reason_note: str = Form(""),
                     received_on: str = Form(""), photos_: list[UploadFile] = File(default=[], alias="photos")):
    actor = actor_of(request)
    if not actor:
        return JSONResponse({"ok": False, "error": "担当者を選んでください"}, status_code=401)
    try:
        res = service.create_return(conn, dict(
            customer=customer, part_no=part_no, product_name=product_name, maker=maker, serial_no=serial_no,
            quantity=quantity, defect=defect, defect_text=defect_text, reason_note=reason_note,
            received_on=received_on, staff=actor), actor)
    except service.BusinessError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    bad = await _save_photos(conn, res["id"], res["receipt_no"], photos_)
    if bad:
        res["warnings"].append(f"{bad}枚の写真は画像として読み込めず、保存できませんでした")
    return {"ok": True, **res}


@app.get("/done/{receipt_no}", response_class=HTMLResponse)
def done(request: Request, receipt_no: str, warn: str = "", conn=Depends(get_conn)):
    r = service.find_by_receipt_no(conn, receipt_no)
    if r is None:
        return RedirectResponse("/", status_code=303)
    return render(request, "done.html", r=r, warnings=[w for w in warn.split("|") if w])


@app.get("/api/suggest")
def api_suggest(kind: str, q: str = "", conn=Depends(get_conn)):
    if kind not in (*masters.SIMPLE_TABLES, "product"):
        return JSONResponse([], status_code=400)
    return masters.suggest(conn, kind, q)


@app.get("/api/product")
def api_product(part_no: str, conn=Depends(get_conn)):
    return masters.find_product(conn, part_no) or {}


# ---- 詳細・状況更新 --------------------------------------------------------

def _get_or_none(conn, receipt_no):
    return service.find_by_receipt_no(conn, receipt_no)


@app.get("/r/{receipt_no}", response_class=HTMLResponse)
def detail(request: Request, receipt_no: str, msg: str = "", err: str = "", conn=Depends(get_conn)):
    if (redir := need_staff(request)):
        return redir
    r = _get_or_none(conn, receipt_no)
    if r is None:
        return RedirectResponse(f"/?err={quote('その受付番号は見つかりませんでした')}", status_code=303)
    i = service.STATUSES.index(r["status"])
    return render(request, "detail.html", r=r, photos=service.photos_of(conn, r["id"]),
                  events=service.events_of(conn, r["id"]), msg=msg, err=err,
                  prev_status=service.STATUSES[i - 1] if i > 0 else None,
                  next_status=service.STATUSES[i + 1] if i < 3 else None,
                  stale_days=service.stale_days(r), level=service.stale_level(conn, r))


@app.post("/r/{receipt_no}/status")
def post_status(request: Request, receipt_no: str, status: str = Form(...), conn=Depends(get_conn)):
    r = _get_or_none(conn, receipt_no)
    if r is None:
        return RedirectResponse("/", status_code=303)
    try:
        service.change_status(conn, r["id"], status, actor_of(request) or "不明")
    except service.BusinessError as e:
        return redirect_detail(r["receipt_no"], err=str(e))
    return redirect_detail(r["receipt_no"], msg=f"「{service.STATUS_LABELS[status]}」にしました")


@app.post("/r/{receipt_no}/disposition")
def post_disposition(request: Request, receipt_no: str, disposition: str = Form(...), conn=Depends(get_conn)):
    r = _get_or_none(conn, receipt_no)
    if r is None:
        return RedirectResponse("/", status_code=303)
    try:
        service.set_disposition(conn, r["id"], disposition, actor_of(request) or "不明")
    except service.BusinessError as e:
        return redirect_detail(r["receipt_no"], err=str(e))
    return redirect_detail(r["receipt_no"], msg=f"処分方法を「{service.DISPOSITION_LABELS[disposition]}」にしました")


@app.get("/r/{receipt_no}/edit", response_class=HTMLResponse)
def edit_form(request: Request, receipt_no: str, conn=Depends(get_conn)):
    if (redir := need_staff(request)):
        return redir
    r = _get_or_none(conn, receipt_no)
    if r is None:
        return RedirectResponse("/", status_code=303)
    return render(request, "form.html", mode="edit", ret=r, **_form_ctx(conn))


@app.post("/api/returns/{rid}/update")
async def api_update(request: Request, rid: int, conn=Depends(get_conn),
                     customer: str = Form(""), part_no: str = Form(""), product_name: str = Form(""),
                     maker: str = Form(""), serial_no: str = Form(""), quantity: str = Form("1"),
                     defect: str = Form(""), defect_text: str = Form(""), reason_note: str = Form(""),
                     received_on: str = Form(""), photos_: list[UploadFile] = File(default=[], alias="photos")):
    actor = actor_of(request) or "不明"
    r = service.get_return(conn, rid)
    if r is None:
        return JSONResponse({"ok": False, "error": "返品が見つかりません"}, status_code=404)
    try:
        res = service.update_return(conn, rid, dict(
            customer=customer, part_no=part_no, product_name=product_name, maker=maker, serial_no=serial_no,
            quantity=quantity, defect=defect, defect_text=defect_text, reason_note=reason_note,
            received_on=received_on), actor)
    except service.BusinessError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    await _save_photos(conn, rid, r["receipt_no"], photos_)
    return {"ok": True, "receipt_no": r["receipt_no"], **res}


@app.get("/photos/{path:path}")
def photo_file(path: str):
    full = (config.photos_dir() / path).resolve()
    if config.photos_dir().resolve() not in full.parents or not full.is_file():
        return Response(status_code=404)
    return FileResponse(full, headers={"Cache-Control": "max-age=86400"})


# ---- 一覧 ------------------------------------------------------------------

FILTER_KEYS = ("q", "status", "disposition", "maker", "customer", "part_no", "date_from", "date_to")


@app.get("/returns", response_class=HTMLResponse)
def list_page(request: Request, page: int = 1, conn=Depends(get_conn)):
    f = {k: request.query_params.get(k, "") for k in FILTER_KEYS}
    f["open_only"] = request.query_params.get("open_only") == "1"
    try:
        rows, total = service.list_returns(conn, f, 50, (max(page, 1) - 1) * 50)
        err = ""
    except service.BusinessError as e:
        rows, total, err = [], 0, str(e)
    items = [{"r": r, "days": service.stale_days(r), "level": service.stale_level(conn, r)} for r in rows]
    qs = "&".join(f"{k}={quote(str(v))}" for k, v in request.query_params.items() if k != "page")
    return render(request, "list.html", items=items, total=total, f=f, page=page, err=err, qs=qs,
                  pages=(total + 49) // 50)


# ---- 印刷 ------------------------------------------------------------------

@app.get("/print-queue", response_class=HTMLResponse)
def print_queue(request: Request, show: str = "unprinted", conn=Depends(get_conn)):
    f = {"unprinted": True} if show == "unprinted" else {}
    rows, total = service.list_returns(conn, f, 200)
    return render(request, "print_queue.html", rows=rows, total=total, show=show)


def _slips_for(conn, request, ids: list[int]):
    ub = base_url(conn, request)
    out = []
    for rid in ids:
        r = service.get_return(conn, rid)
        if r:
            out.append((r, slip_dict(r, ub)))
    return out


def _parse_ids(ids: str) -> list[int]:
    return [int(x) for x in ids.split(",") if x.strip().isdigit()]


def _layout(v: str) -> str:
    return v if v in slip.LAYOUTS else "a5"


@app.get("/print/batch", response_class=HTMLResponse)
def print_batch(request: Request, ids: str = "", layout: str = "a5", conn=Depends(get_conn)):
    id_list = _parse_ids(ids)
    pairs = _slips_for(conn, request, id_list)
    return render(request, "print.html", pairs=[(r, s, qr_svg(s["url"])) for r, s in pairs],
                  layout=_layout(layout), ids=",".join(map(str, id_list)), back="/print-queue")


@app.get("/print/batch.pdf")
def print_batch_pdf(request: Request, ids: str = "", layout: str = "a5", conn=Depends(get_conn)):
    pairs = _slips_for(conn, request, _parse_ids(ids))
    pdf = slip.render_pdf([s for _, s in pairs], _layout(layout))
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="slips.pdf"'})


@app.get("/print/{receipt_no}", response_class=HTMLResponse)
def print_one(request: Request, receipt_no: str, layout: str = "a5", conn=Depends(get_conn)):
    r = _get_or_none(conn, receipt_no)
    if r is None:
        return RedirectResponse("/", status_code=303)
    s = slip_dict(r, base_url(conn, request))
    return render(request, "print.html", pairs=[(r, s, qr_svg(s["url"]))], layout=_layout(layout),
                  ids=str(r["id"]), back=f"/r/{r['receipt_no']}")


@app.get("/r/{receipt_no}/slip.pdf")
def slip_pdf(request: Request, receipt_no: str, layout: str = "a5", conn=Depends(get_conn)):
    r = _get_or_none(conn, receipt_no)
    if r is None:
        return Response(status_code=404)
    pdf = slip.render_pdf([slip_dict(r, base_url(conn, request))], _layout(layout))
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{r["receipt_no"]}.pdf"'})


@app.post("/api/printed")
async def api_printed(request: Request, conn=Depends(get_conn)):
    body = await request.json()
    service.mark_printed(conn, [int(i) for i in body.get("ids", [])], actor_of(request) or "不明")
    return {"ok": True}
