"""写真の保存。アップロード時に自動で縮小して容量を抑える。"""
import io
import uuid
from pathlib import Path

from PIL import Image, ImageOps

from . import config
from .db import now_iso

MAX_SIDE = 1280
THUMB_SIDE = 320


class PhotoError(ValueError):
    pass


def save_photo(conn, return_id: int, receipt_no: str, data: bytes) -> int:
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as e:  # 画像でないファイル
        raise PhotoError("画像として読み込めませんでした") from e
    rel_dir = Path(receipt_no[3:7]) / receipt_no  # 例: 2026/RT-20261008-001
    out_dir = config.photos_dir() / rel_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    name = uuid.uuid4().hex[:10]
    big = img.copy()
    big.thumbnail((MAX_SIDE, MAX_SIDE))
    big.save(out_dir / f"{name}.jpg", "JPEG", quality=80, optimize=True)
    img.thumbnail((THUMB_SIDE, THUMB_SIDE))
    img.save(out_dir / f"{name}_t.jpg", "JPEG", quality=70)
    cur = conn.execute(
        "INSERT INTO return_photos(return_id,file_path,thumb_path,taken_at) VALUES(?,?,?,?)",
        (return_id, str(rel_dir / f"{name}.jpg"), str(rel_dir / f"{name}_t.jpg"), now_iso()),
    )
    return cur.lastrowid
