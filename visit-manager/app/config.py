"""設定と日本時間(Asia/Tokyo)の扱い。"""
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo

    JST = ZoneInfo("Asia/Tokyo")
    datetime.now(JST)
except Exception:  # tzdata が無い環境でも日本は夏時間が無いので固定+9時間で代替
    JST = timezone(timedelta(hours=9))

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("VM_DB_PATH", BASE_DIR / "data" / "visits.db"))
# HTTPS で運用する場合は VM_SECURE_COOKIE=1
SECURE_COOKIE = os.environ.get("VM_SECURE_COOKIE", "0") == "1"
SESSION_DAYS = 14
DEFAULT_THRESHOLD_DAYS = 30


def now_jst() -> datetime:
    return datetime.now(JST)


def today_jst() -> date:
    return now_jst().date()
