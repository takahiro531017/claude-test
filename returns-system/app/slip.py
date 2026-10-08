"""受付票(A5)のPDF生成。ブラウザ印刷用HTMLと同じレイアウトを紙面寸法(mm)で描く。"""
import io
from functools import lru_cache

import segno
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from . import config

FONT = "IPAexGothic"
A5_W, A5_H = 148.0, 210.0  # 縦
A4_W, A4_H = 210.0, 297.0
LAYOUTS = ("a5", "a4_2up")


@lru_cache(maxsize=1)
def _register_font() -> str:
    pdfmetrics.registerFont(TTFont(FONT, str(config.BASE_DIR / "fonts" / "ipaexg.ttf")))
    return FONT


def page_size_mm(layout: str) -> tuple[float, float]:
    if layout == "a5":
        return A5_W, A5_H
    if layout == "a4_2up":
        return A4_H, A4_W  # A4横に縦のA5を2枚
    raise ValueError(f"unknown layout: {layout}")


def wrap(text: str, size: float, width_pt: float) -> list[str]:
    """日本語は文字単位で折り返す。改行コードは尊重する。"""
    lines: list[str] = []
    for para in (text or "").splitlines() or [""]:
        cur = ""
        for ch in para:
            if stringWidth(cur + ch, FONT, size) > width_pt and cur:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        lines.append(cur)
    return lines


def fit(text: str, size: float, min_size: float, width_pt: float, max_lines: int):
    """収まるまで文字を縮小し、それでも超えれば末尾を「…」で省略する。"""
    s = size
    while True:
        lines = wrap(text, s, width_pt)
        if len(lines) <= max_lines:
            return s, lines
        if s <= min_size:
            lines = lines[:max_lines]
            last = lines[-1]
            while last and stringWidth(last + "…", FONT, s) > width_pt:
                last = last[:-1]
            lines[-1] = last + "…"
            return s, lines
        s -= 1


def _draw_qr(c, url: str, x: float, y: float, size: float):
    """x,y は左下(pt)。QRの周囲に白い余白(クワイエットゾーン)を確保する。"""
    qr = segno.make(url, error="m", micro=False)
    matrix = [list(row) for row in qr.matrix]
    n = len(matrix)
    quiet = 2 * mm
    cell = (size - 2 * quiet) / n
    c.setFillColorRGB(1, 1, 1)
    c.rect(x, y, size, size, stroke=0, fill=1)
    c.setFillColorRGB(0, 0, 0)
    for r, row in enumerate(matrix):
        for col, v in enumerate(row):
            if v:
                c.rect(x + quiet + col * cell, y + size - quiet - (r + 1) * cell, cell + 0.15, cell + 0.15,
                       stroke=0, fill=1)


# 行の定義: (ラベル, スリップのキー, 文字サイズ, 最小サイズ, 最大行数, 行の高さmm)
ROWS = [
    ("返品元", "customer", 16, 10, 1, 13),
    ("品番", "part_no", 26, 12, 1, 17),
    ("商品名", "product_name", 16, 10, 2, 20),
    ("メーカー", "maker", 16, 10, 1, 13),
    ("製造No.", "serial_no", 18, 10, 1, 14),
    ("不良内容", "defect", 18, 10, 2, 20),
]


def draw_slip(c, x0: float, y0: float, slip: dict):
    """A5縦(148x210mm)の受付票を、左下が (x0,y0) pt の位置に描く。"""
    W, H = A5_W * mm, A5_H * mm
    m = 8 * mm
    top = y0 + H - m
    c.setStrokeColorRGB(0, 0, 0)
    c.setFillColorRGB(0, 0, 0)
    # タイトル行
    c.setFont(FONT, 15)
    c.drawString(x0 + m, top - 5.5 * mm, "返品受付票")
    c.setFont(FONT, 14)
    c.drawRightString(x0 + W - m, top - 5.5 * mm, slip["received_on"].replace("-", "/"))
    c.setLineWidth(0.8)
    c.line(x0 + m, top - 8 * mm, x0 + W - m, top - 8 * mm)
    # 受付番号(大)とQR
    qr_size = 38 * mm
    qr_x = x0 + W - m - qr_size
    qr_y = top - 10 * mm - qr_size
    _draw_qr(c, slip["url"], qr_x, qr_y, qr_size)
    c.setFont(FONT, 8)
    c.drawCentredString(qr_x + qr_size / 2, qr_y - 3.2 * mm, "スマホで読み取り")
    num_w = qr_x - (x0 + m) - 3 * mm
    c.setFont(FONT, 9)
    c.drawString(x0 + m, top - 15 * mm, "受付番号")
    size, lines = fit(slip["receipt_no"], 40, 14, num_w, 1)
    c.setFont(FONT, size)
    c.drawString(x0 + m, top - 15 * mm - size * 0.95, lines[0])
    # 数量・担当者(番号の下)
    c.setFont(FONT, 9)
    c.drawString(x0 + m, qr_y + 17 * mm, "数量")
    c.setFont(FONT, 28)
    c.drawString(x0 + m, qr_y + 8 * mm, f"{slip['quantity']} 個")
    c.setFont(FONT, 9)
    c.drawString(x0 + m + 42 * mm, qr_y + 17 * mm, "担当者")
    s2, l2 = fit(slip["staff"], 18, 10, num_w - 42 * mm, 1)
    c.setFont(FONT, s2)
    c.drawString(x0 + m + 42 * mm, qr_y + 9 * mm, l2[0])
    # 項目行
    y = qr_y - 8 * mm
    inner_w = W - 2 * m
    label_w = 24 * mm
    c.setLineWidth(0.4)
    for label, key, size, min_size, max_lines, h in ROWS:
        c.line(x0 + m, y, x0 + W - m, y)
        c.setFont(FONT, 9)
        c.drawString(x0 + m, y - 4.5 * mm, label)
        s, lines = fit(slip.get(key) or "", size, min_size, inner_w - label_w, max_lines)
        c.setFont(FONT, s)
        ty = y - (4 * mm + s * 0.9)
        for ln in lines:
            c.drawString(x0 + m + label_w, ty, ln)
            ty -= s * 1.15
        y -= h * mm
    c.line(x0 + m, y, x0 + W - m, y)
    # 備考(手書き欄)
    c.setFont(FONT, 9)
    c.drawString(x0 + m, y - 4.5 * mm, "備考")
    c.setLineWidth(0.3)
    c.setStrokeColorRGB(0.6, 0.6, 0.6)
    ly = y - 12 * mm
    while ly > y0 + m:
        c.line(x0 + m, ly, x0 + W - m, ly)
        ly -= 8 * mm


def _cut_marks(c, x: float, page_h: float):
    """A4に2枚並べるときの切り取り線とトンボ。"""
    c.saveState()
    c.setStrokeColorRGB(0.3, 0.3, 0.3)
    c.setLineWidth(0.4)
    c.setDash(3, 3)
    c.line(x, 6 * mm, x, page_h - 6 * mm)
    c.setDash()
    for y in (4 * mm, page_h - 4 * mm):  # トンボ(上下端の短い実線)
        c.line(x, y - 2 * mm, x, y + 2 * mm)
        c.line(x - 3 * mm, y, x + 3 * mm, y)
    c.setFont(FONT, 7)
    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.saveState()
    c.translate(x + 2.5 * mm, page_h / 2)
    c.rotate(90)
    c.drawCentredString(0, 0, "切り取り線")
    c.restoreState()
    c.restoreState()


def render_pdf(slips: list[dict], layout: str = "a5", offset_x_mm: float = 0.0, offset_y_mm: float = 0.0) -> bytes:
    """受付票PDFを作る。offset は印刷位置の微調整(mm。右・上がプラス)。"""
    _register_font()
    pw, ph = page_size_mm(layout)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(pw * mm, ph * mm), pageCompression=0)
    c.setTitle("返品受付票")
    per_page = 2 if layout == "a4_2up" else 1
    slips = slips or []
    for i in range(0, max(len(slips), 1), per_page):
        chunk = slips[i:i + per_page]
        c.translate(offset_x_mm * mm, offset_y_mm * mm)
        for j, slip in enumerate(chunk):
            draw_slip(c, j * A5_W * mm + (pw - per_page * A5_W) / 2 * mm, 0, slip)
        if layout == "a4_2up":
            _cut_marks(c, pw / 2 * mm, ph * mm)
        c.showPage()
    c.save()
    return buf.getvalue()
