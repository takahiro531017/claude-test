"""ローカル専用の防御層: Host/Origin 検査（DNSリバインディング・CSRF対策）、CSP、任意のパスワード保護。"""
from __future__ import annotations

import base64
import hmac
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

LOOPBACK = {"localhost", "127.0.0.1", "[::1]", "::1"}
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CSP = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"


def _host(value: str) -> str:
    return (urlsplit("//" + value).hostname or "").lower() if not value.startswith("[") else value.split("]")[0] + "]"


def install(app, allowed_hosts: set[str], password: str | None) -> None:
    """将来のパスワード保護: password を渡す（環境変数 FARE_HUB_PASSWORD）と全リクエストに Basic 認証を要求。"""

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if _host(request.headers.get("host", "")) not in allowed_hosts:
            return PlainTextResponse("bad host", status_code=400)
        origin = request.headers.get("origin")
        if request.method in UNSAFE and origin and _host(urlsplit(origin).netloc) not in allowed_hosts:
            return PlainTextResponse("forbidden origin", status_code=403)
        if password:
            ok = False
            auth = request.headers.get("authorization", "")
            if auth.lower().startswith("basic "):
                try:
                    _, _, given = base64.b64decode(auth[6:]).decode("utf-8").partition(":")
                    ok = hmac.compare_digest(given.encode(), password.encode())
                except Exception:
                    ok = False
            if not ok:
                return Response("auth required", status_code=401, headers={"WWW-Authenticate": 'Basic realm="fare-hub"'})
        resp = await call_next(request)
        resp.headers["Content-Security-Policy"] = CSP
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Cache-Control"] = "no-store"
        return resp
