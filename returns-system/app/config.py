"""設定値(場所の指定など)。環境変数で上書きできます。"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def data_dir() -> Path:
    """DB・写真・出力PDFを置くフォルダ。バックアップ対象はこのフォルダ全体。"""
    d = Path(os.environ.get("RETURNS_DATA_DIR") or BASE_DIR.parent / "data")
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return data_dir() / "returns.sqlite3"


def photos_dir() -> Path:
    d = data_dir() / "photos"
    d.mkdir(parents=True, exist_ok=True)
    return d


# 設定画面ができるまでの暫定:環境変数 RETURNS_BASE_URL(例 http://returns.local:8000)
def env_base_url() -> str:
    return (os.environ.get("RETURNS_BASE_URL") or "").rstrip("/")
