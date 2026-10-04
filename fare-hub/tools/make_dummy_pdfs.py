"""ダミー運賃表PDFの生成（テスト・動作確認用）。

値はすべて乱数（100〜999円）と架空名。実データは一切含まない。
  python -m tools.make_dummy_pdfs [出力先ディレクトリ]   # 既定: data/dummy/（Git管理外）
"""
from __future__ import annotations

import io
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from app.config import load_settings

FONT = "HeiseiKakuGo-W5"
PAGE = (842, 595)  # A4 横

NOTES = [
    "※沖縄は別料金となります（別途お見積り）。",
    "※一部離島は別途中継料がかかります。",
    "※運送保険：荷物価額に対し所定の料率（ダミー0.3%）を適用します。",
    "※想定月間出荷個数：ダミー100個。大きく下回る場合は運賃を見直します（見直し条件）。",
    "※サイズ上限：3辺合計260cm以内、重量50kg以内。",
]


@dataclass
class Spec:
    origin: str
    valid_from: str = "2025年4月1日"
    valid_to: str = "2026年3月31日"
    layout: str = "standard"  # standard | alt
    seed: int = 1
    missing: list[tuple[str, int]] = field(default_factory=list)  # 空欄にするセル
    dashed: list[tuple[str, int]] = field(default_factory=list)  # 「-」にするセル
    notes: list[str] = field(default_factory=lambda: list(NOTES))
    customer_code: str = "C-0001"
    quote_no: str = "Q-2025-001"


def make_rates(spec: Spec) -> dict[tuple[str, int], int]:
    st = load_settings()
    rnd = random.Random(spec.seed)
    return {(r, s): rnd.randint(100, 999) for r in st.region_names for s in st.sizes}


def _draw(c: canvas.Canvas, spec: Spec, rates: dict[tuple[str, int], int]) -> None:
    st = load_settings()
    alt = spec.layout == "alt"
    rnd = random.Random(spec.seed + 99)

    # --- ヘッダー ---
    items: list[tuple[float, float, str, float]] = []  # (x, y, text, font)
    items.append((40, 560, "運賃表（ダミー）", 14))
    if not alt:
        # 1行に2項目を並べるレイアウト
        items += [
            (40, 535, f"運賃適用期日：{spec.valid_from}", 9),
            (300, 535, f"運賃満期日：{spec.valid_to}", 9),
            (40, 520, f"発地：{spec.origin}", 9),
            (300, 520, f"顧客コード：{spec.customer_code}", 9),
            (40, 505, f"見積No.：{spec.quote_no}", 9),
            (300, 505, "支払条件：月末締め翌月末払い", 9),
            (560, 505, "締日：月末", 9),
        ]
        col0, step, label_x, pref_x = 300.0, 45.0, 40.0, 90.0
        header_y, row_y0, row_dy = 470.0, 430.0, 22.0
        order = list(st.region_names)
        names = {r: r for r in order}
    else:
        # 1行1項目・別ラベル・別名の地帯・逆順
        items += [
            (40, 540, f"適用開始日　{spec.valid_from}", 9),
            (40, 527, f"有効期限　{spec.valid_to}", 9),
            (40, 514, f"出荷元　{spec.origin}", 9),
            (40, 501, f"お客様コード　{spec.customer_code}", 9),
            (40, 488, f"見積番号　{spec.quote_no}", 9),
            (400, 540, "お支払条件　20日締め翌月払い", 9),
            (400, 527, "締め日　20日", 9),
        ]
        col0, step, label_x, pref_x = 270.0, 48.0, 36.0, 100.0
        header_y, row_y0, row_dy = 455.0, 415.0, 21.0
        order = list(reversed(st.region_names))
        names = {r: r for r in order}
        names["南九州"], names["北九州"] = "九州南部", "九州北部"

    # --- マトリクス見出し ---
    items.append((label_x, header_y, "着地＼サイズ", 8))
    for i, s in enumerate(st.sizes):
        items.append((col0 + i * step, header_y, str(s), 9))
    for i, s in enumerate(st.sizes):
        if s in st.weight_sizes:
            items.append((col0 + i * step, header_y - 11, f"{st.weight_sizes[s]}kg", 6.5))

    # --- 本体 ---
    prefs = {r.name: "・".join(p[:-1] if p != "北海道" else p for p in r.prefectures)
             for r in st.regions}
    for ri, region in enumerate(order):
        y = row_y0 - ri * row_dy
        items.append((label_x, y, names[region], 9))
        items.append((pref_x, y, prefs[region], 6.5))
        for ci, s in enumerate(st.sizes):
            key = (region, s)
            x = col0 + ci * step
            if key in spec.missing:
                continue
            if key in spec.dashed:
                items.append((x, y, "-", 9))
            else:
                items.append((x, y, f"{rates[key]:,}", 9))

    # --- 注記 ---
    ny = row_y0 - len(order) * row_dy - 12
    items.append((40, ny, "注記", 9))
    for i, n in enumerate(spec.notes):
        items.append((40, ny - 13 * (i + 1), n, 8))
    items.append((420, 20, "1 / 1", 8))  # ページ番号（無視されること）

    # 描画順をシャッフルして「テキスト抽出順が崩れる」状況を再現
    rnd.shuffle(items)
    for x, y, text, size in items:
        c.setFont(FONT, size)
        c.drawString(x, y, text)


def build_pdf(spec: Spec, path: str | Path | None = None) -> bytes:
    """PDFを生成してバイト列を返す（path 指定時はファイルにも書く）。"""
    try:
        pdfmetrics.getFont(FONT)
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont(FONT))
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=PAGE, invariant=1)  # 決定的な出力
    _draw(c, spec, make_rates(spec))
    c.showPage()
    c.save()
    data = buf.getvalue()
    if path:
        Path(path).write_bytes(data)
    return data


def default_specs() -> list[Spec]:
    return [
        Spec("拠点A", seed=1),
        Spec("拠点B", layout="alt", seed=2, valid_from="2025年6月1日", valid_to="2027年5月31日"),
        Spec("拠点C", seed=3, valid_from="2024年4月1日", valid_to="2025年3月31日",
             missing=[("関東", 100), ("北海道", 260)], dashed=[("四国", 60)]),
    ]


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "data/dummy")
    out.mkdir(parents=True, exist_ok=True)
    for sp in default_specs():
        p = out / f"dummy_{sp.origin}.pdf"
        build_pdf(sp, p)
        print("wrote", p)


if __name__ == "__main__":
    main()
