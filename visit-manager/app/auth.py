import hashlib
import secrets
import time
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError

from . import config

_ph = PasswordHasher()
_ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# ログイン失敗の簡易ロック(プロセス内メモリ)
_fails: dict[str, list[float]] = {}
MAX_FAILS, LOCK_SEC = 5, 300


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(h: str, pw: str) -> bool:
    try:
        return _ph.verify(h, pw)
    except (VerifyMismatchError, InvalidHashError):
        return False


def temp_password(n: int = 10) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


def validate_new_password(user_id: str, pw: str) -> str | None:
    if len(pw) < 8:
        return "パスワードは8文字以上にしてください"
    if pw.lower() == user_id.lower():
        return "IDと同じパスワードは使えません"
    if pw.isdigit() or pw.isalpha():
        return "英字と数字の両方を含めてください"
    return None


def is_locked(key: str) -> bool:
    now = time.time()
    recent = [t for t in _fails.get(key, []) if now - t < LOCK_SEC]
    _fails[key] = recent
    return len(recent) >= MAX_FAILS


def record_fail(key: str) -> None:
    _fails.setdefault(key, []).append(time.time())


def clear_fails(key: str) -> None:
    _fails.pop(key, None)


def _th(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(conn, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    exp = (config.now_jst() + timedelta(days=config.SESSION_DAYS)).isoformat()
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (config.now_jst().isoformat(),))
    conn.execute("INSERT INTO sessions VALUES (?,?,?)", (_th(token), user_id, exp))
    conn.commit()
    return token


def user_for_token(conn, token: str | None):
    if not token:
        return None
    return conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id "
        "WHERE s.token_hash=? AND s.expires_at>? AND u.active=1",
        (_th(token), config.now_jst().isoformat()),
    ).fetchone()


def drop_session(conn, token: str | None, user_id: str | None = None) -> None:
    if token:
        conn.execute("DELETE FROM sessions WHERE token_hash=?", (_th(token),))
    if user_id:
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    conn.commit()
