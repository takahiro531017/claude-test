"""FastAPI アプリ。localhost のみで使う想定（run.py が 127.0.0.1 に固定バインド）。"""
from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, exporter, security, service
from .config import load_settings

STATIC = Path(__file__).parent / "static"
log = logging.getLogger("fare_hub")


class RateIn(BaseModel):
    region: str
    size: int
    price: int | None = Field(default=None, description="null で削除（欠損に戻す）")


class MetaIn(BaseModel):
    origin: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    customer_code: str | None = None
    quote_no: str | None = None
    payment_terms: str | None = None
    closing_day: str | None = None


def create_app(db_path=None, password: str | None = None, today: date | None = None,
               allowed_hosts: set[str] | None = None) -> FastAPI:
    st = load_settings()
    path = db_path or db.default_db_path()
    # docs/openapi は外部CDNから資産を読むため無効化（外部通信禁止）
    app = FastAPI(title="fare-hub", docs_url=None, redoc_url=None, openapi_url=None)
    security.install(app, allowed_hosts or security.LOOPBACK,
                     password if password is not None else os.environ.get("FARE_HUB_PASSWORD") or None)

    def get_conn():
        conn = db.connect(path)
        try:
            yield conn
        finally:
            conn.close()

    def now() -> date:
        return today or date.today()

    @app.post("/api/import")
    async def import_files(files: list[UploadFile] = File(...), conn=Depends(get_conn)):
        limit = st.parser["limits"]["max_file_mb"] * 1024 * 1024
        results = []
        for f in files:
            data = await f.read(limit + 1)  # 巨大ファイルは先頭だけ読んで拒否
            results.append(await run_in_threadpool(service.import_pdf, conn, st, f.filename or "", data))
        return {"results": results}

    @app.get("/api/meta")
    def meta():
        return {"sizes": st.sizes, "weight_sizes": st.weight_sizes, "special_prefectures": st.special_prefectures,
                "regions": [{"name": r.name, "aliases": r.aliases, "prefectures": r.prefectures} for r in st.regions],
                "note_categories": st.parser["notes"]["categories"], "today": now().isoformat()}

    @app.get("/api/tariffs")
    def tariffs(conn=Depends(get_conn)):
        return service.list_tariffs(conn, st, now())

    @app.get("/api/tariffs/{tid}")
    def tariff(tid: int, conn=Depends(get_conn)):
        d = service.get_tariff(conn, st, tid, now())
        if not d:
            raise HTTPException(404, "tariff_not_found")
        return d

    @app.delete("/api/tariffs/{tid}")
    def delete_tariff(tid: int, conn=Depends(get_conn)):
        if not service.delete_tariff(conn, tid):
            raise HTTPException(404, "tariff_not_found")
        return {"ok": True}

    @app.put("/api/tariffs/{tid}")
    def update_meta(tid: int, body: MetaIn, conn=Depends(get_conn)):
        try:
            service.update_meta(conn, tid, body.model_dump(exclude_unset=True))
        except LookupError:
            raise HTTPException(404, "tariff_not_found")
        except ValueError as e:
            raise HTTPException(422, str(e))
        return service.get_tariff(conn, st, tid, now())

    @app.put("/api/tariffs/{tid}/rates")
    def update_rate(tid: int, body: RateIn, conn=Depends(get_conn)):
        try:
            service.set_rate(conn, st, tid, body.region, body.size, body.price)
        except LookupError:
            raise HTTPException(404, "tariff_not_found")
        except ValueError as e:
            raise HTTPException(422, str(e))
        return service.get_tariff(conn, st, tid, now())

    @app.get("/api/lookup")
    def lookup(dest: str, size: int | None = None, origin: str | None = None, conn=Depends(get_conn)):
        return service.lookup(conn, st, now(), dest, size, origin)

    @app.get("/api/combined")
    def combined(conn=Depends(get_conn)):
        rows = service.combined_rows(conn, st, now())
        best = service.cheapest(rows)
        return {"rows": rows, "cheapest": {f"{r}|{s}": p for (r, s), p in best.items()},
                "tariffs": service.current_tariffs(conn, st, now())}

    @app.get("/api/notes")
    def notes(conn=Depends(get_conn)):
        out = []
        for t in service.current_tariffs(conn, st, now()):
            d = service.get_tariff(conn, st, t["id"], now())
            out.append({"tariff_id": t["id"], "origin": t["origin"], "status": t["status"], "notes": d["notes"]})
        return out

    @app.get("/api/export.csv")
    def export_csv(conn=Depends(get_conn)):
        return Response(exporter.to_csv(conn, st, now()), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="fare_hub.csv"'})

    @app.get("/api/export.xlsx")
    def export_xlsx(conn=Depends(get_conn)):
        return Response(exporter.to_xlsx(conn, st, now()),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": 'attachment; filename="fare_hub.xlsx"'})

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
