"""伝票ファイルの走査・PDF分割・画像の向き補正と縮小。"""
from __future__ import annotations

import hashlib
import io
import logging
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

log = logging.getLogger(__name__)

IMAGE_EXT = {".jpg", ".jpeg", ".png"}
PDF_EXT = {".pdf"}


@dataclass
class PageRef:
    path: Path
    page: int            # 1始まり（画像は1）
    pages_total: int
    file_hash: str
    error: str | None = None

    @property
    def key(self) -> str:
        return f"{self.file_hash}:{self.page}"

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def label(self) -> str:
        return f"{self.path.name}（{self.page}ページ目）" if self.pages_total > 1 else self.path.name


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_folder(folder: Path, recursive: bool = False) -> list[Path]:
    it = folder.rglob("*") if recursive else folder.iterdir()
    files = [
        p for p in it
        if p.is_file() and p.suffix.lower() in IMAGE_EXT | PDF_EXT and not p.name.startswith(("_", ".", "~"))
    ]
    return sorted(files, key=lambda p: str(p).lower())


def collect_pages(folder: Path, recursive: bool = False, max_pdf_pages: int = 200) -> list[PageRef]:
    """フォルダ内の全ファイルをページ単位に展開する。開けないファイルはerror付きの1件にする。"""
    refs: list[PageRef] = []
    for path in scan_folder(folder, recursive):
        try:
            fh = sha256_file(path)
        except OSError as e:
            refs.append(PageRef(path, 1, 1, f"unreadable:{path.name}", f"ファイルを開けません: {e}"))
            continue
        if path.suffix.lower() in PDF_EXT:
            try:
                import pymupdf as fitz

                with fitz.open(path) as doc:
                    n = doc.page_count
                if n == 0:
                    raise ValueError("ページがありません")
            except Exception as e:  # 壊れたPDF・パスワード付き等
                refs.append(PageRef(path, 1, 1, fh, f"PDFを開けません: {e}"))
                continue
            for i in range(1, min(n, max_pdf_pages) + 1):
                refs.append(PageRef(path, i, n, fh))
        else:
            refs.append(PageRef(path, 1, 1, fh))
    return refs


def render_page(ref: PageRef, dpi: int = 200) -> Image.Image:
    """ページを向き補正済みのRGB画像にして返す。"""
    if ref.path.suffix.lower() in PDF_EXT:
        import pymupdf as fitz

        with fitz.open(ref.path) as doc:
            pix = doc.load_page(ref.page - 1).get_pixmap(dpi=dpi, alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            img.load()
    else:
        img = Image.open(ref.path)
        img.load()
        img = ImageOps.exif_transpose(img)  # スマホ・スキャナのEXIF向きを補正
    return _to_rgb(img)


def _to_rgb(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, "white")
        bg.paste(img, mask=img.split()[-1])
        return bg
    return img.convert("RGB")


def shrink(img: Image.Image, max_long_edge: int) -> Image.Image:
    w, h = img.size
    long_edge = max(w, h)
    if long_edge <= max_long_edge:
        return img
    scale = max_long_edge / long_edge
    return img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)


def prepare_for_api(ref: PageRef, max_long_edge: int = 1568, quality: int = 85, dpi: int = 200) -> bytes:
    """APIに送るJPEGバイト列（向き補正・長辺縮小済み）。"""
    img = shrink(render_page(ref, dpi), max_long_edge)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return buf.getvalue()
