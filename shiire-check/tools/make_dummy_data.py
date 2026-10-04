"""テスト用のダミー伝票画像・PDF・仕入一覧表Excel・モック読み取り定義を生成する。

使い方:  python tools/make_dummy_data.py [出力先フォルダ]   （省略時は sample_data/）
出力:
  <出力先>/slips/            ダミー伝票（JPG/PNG/PDF）と _mock_readings.json（モック読み取りの定義）
  <出力先>/仕入一覧表.xlsx    ダミーの仕入一覧表（見出し: 仕入日/メーカー/伝票番号/金額/備考）
実在の会社・取引とは無関係の架空データです。
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_CANDIDATES = [
    "C:/Windows/Fonts/meiryo.ttc", "C:/Windows/Fonts/msgothic.ttc", "C:/Windows/Fonts/YuGothM.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    raise SystemExit("日本語フォントが見つかりません。FONT_CANDIDATES にフォントのパスを追加してください。")


def _canvas(w, h):
    img = Image.new("RGB", (w, h), "white")
    return img, ImageDraw.Draw(img)


def _box_title(d, w, title, maker):
    d.rectangle([20, 20, w - 20, 130], outline="black", width=3)
    d.text((50, 40), title, font=_font(56), fill="black")
    d.text((w - 560, 55), maker, font=_font(34), fill="black")


def slip_yamada(no, order, date, total):
    img, d = _canvas(1240, 1754)
    _box_title(d, 1240, "納 品 書", "山田製作所")
    d.text((80, 200), f"納品書No. {no}", font=_font(44), fill="black")
    d.text((80, 280), f"注文番号: {order}", font=_font(30), fill="black")
    d.text((80, 340), f"納品日: {date}", font=_font(30), fill="black")
    for i in range(6):
        d.line([80, 500 + i * 90, 1160, 500 + i * 90], fill="gray", width=2)
        d.text((100, 515 + i * 90), f"部品 {chr(65 + i)}-{100 + i}    x {i + 1}", font=_font(28), fill="black")
    d.text((700, 1150), f"合計 ¥{total:,}", font=_font(44), fill="black")
    return img


def slip_tokai(no, order, date, total, extra=None):
    img, d = _canvas(1600, 900)
    d.rectangle([10, 10, 1590, 890], outline="navy", width=6)
    d.text((50, 40), "仕入伝票  東海部品株式会社", font=_font(44), fill="navy")
    d.text((50, 140), f"伝票番号  {no}", font=_font(52), fill="black")
    d.text((50, 230), f"発注No {order}", font=_font(30), fill="black")
    if extra:
        d.text((900, 140), f"納品書番号  {extra}", font=_font(40), fill="black")
    d.text((50, 300), f"日付 {date}", font=_font(30), fill="black")
    d.text((1000, 780), f"合計 {total:,} 円", font=_font(40), fill="black")
    return img


def slip_hokuto(no, date, total):
    img, d = _canvas(600, 1000)
    d.text((40, 30), "北斗化学(株)", font=_font(40), fill="black")
    d.text((40, 100), "納 品 受 領 書", font=_font(30), fill="black")
    d.text((40, 180), f"受領番号：{no}", font=_font(34), fill="black")
    d.text((40, 240), date, font=_font(26), fill="black")
    d.text((40, 800), f"お買上計 ￥{total:,}", font=_font(32), fill="black")
    return img.rotate(4, expand=True, fillcolor="white", resample=Image.BICUBIC)   # 斜めに


def slip_handwritten(no, maker="丸山商会"):
    """手書き風: 1文字ずつ位置・角度を揺らす。"""
    rnd = random.Random(7)
    img, d = _canvas(1100, 700)
    d.text((40, 30), f"{maker}　仕入メモ", font=_font(36), fill="#333")
    x = 80
    for ch in f"No. {no}":
        g = Image.new("RGBA", (120, 120), (255, 255, 255, 0))
        ImageDraw.Draw(g).text((20, 10), ch, font=_font(rnd.randint(70, 90)), fill=(20, 20, 120, 255))
        g = g.rotate(rnd.randint(-14, 14), resample=Image.BICUBIC)
        img.paste(g, (x, 200 + rnd.randint(-12, 12)), g)
        x += rnd.randint(52, 68)
    return img


def slip_daiwa(no, total, date="2026-10-02"):
    img, d = _canvas(1240, 1754)
    d.text((60, 60), "大和電機 出荷明細", font=_font(48), fill="black")
    d.text((60, 160), f"出荷No: {no}", font=_font(42), fill="black")
    d.text((60, 230), f"出荷日: {date}", font=_font(28), fill="black")
    d.text((700, 1000), f"請求額 {total:,}", font=_font(40), fill="black")
    return img


def slip_simple(maker, label, no, total=None):
    img, d = _canvas(1000, 700)
    d.text((40, 40), maker, font=_font(44), fill="black")
    d.text((40, 160), f"{label} {no}", font=_font(48), fill="black")
    if total:
        d.text((40, 500), f"合計 {total:,}円", font=_font(36), fill="black")
    return img


def with_exif_rotation(img, path):
    """EXIFの向き情報つきで保存（スマホ撮影・スキャナの横向き保存を再現）。"""
    stored = img.rotate(90, expand=True)           # 見た目が横倒しの画素
    exif = Image.Exif()
    exif[0x0112] = 6                               # 「右に90度回して表示」
    stored.save(path, "JPEG", quality=90, exif=exif)


def generate(out: Path) -> dict:
    out = Path(out)
    slips = out / "slips"
    slips.mkdir(parents=True, exist_ok=True)
    for f in slips.iterdir():
        if f.is_file():
            f.unlink()
    mock: dict = {}

    def R(nums, maker=None, date=None, total=None, hw=False, conf="high", note=""):
        return {"slip_numbers": nums, "maker": maker, "date": date, "total_amount": total,
                "handwritten": hw, "confidence": conf, "note": note}

    # 1) 一致（山田製作所・A4縦）
    slip_yamada("2026-10-0001", "PO-88231", "2026年10月1日", 128000).save(slips / "山田製作所_001.jpg", quality=90)
    mock["山田製作所_001.jpg"] = R(["2026-10-0001"], "山田製作所", "2026-10-01", 128000, note="鮮明")
    # 2) 同じ伝票を二重にスキャン（重複警告）
    slip_yamada("2026-10-0001", "PO-88231", "2026年10月1日", 128000).save(slips / "山田製作所_001_再スキャン.jpg", quality=70)
    mock["山田製作所_001_再スキャン.jpg"] = R(["2026-10-0001"], "山田製作所", "2026-10-01", 128000)
    # 3) 表記ゆれ: 伝票「TK-00123」/ 一覧「TK-123」→ 一致（東海部品・横長）
    slip_tokai("TK-00123", "55012", "2026/10/02", 33000).save(slips / "東海部品_a.png")
    mock["東海部品_a.png"] = R(["TK-00123"], "東海部品株式会社", "2026-10-02", 33000)
    # 4) 候補が複数だが一覧に存在するのは1つ → 一致（備考に注記）
    slip_tokai("TK-00124", "55013", "2026/10/02", 8800, extra="NK-9001").save(slips / "東海部品_b.png")
    mock["東海部品_b.png"] = R(["TK-00124", "NK-9001"], "東海部品株式会社", "2026-10-02", 8800, conf="medium", note="伝票番号と納品書番号の2種類あり")
    # 5) 候補が複数で、どれも一覧にない → 要確認
    slip_tokai("ZZ-100", "55014", "2026/10/02", 1200, extra="ZZ-200").save(slips / "東海部品_c.png")
    mock["東海部品_c.png"] = R(["ZZ-100", "ZZ-200"], "東海部品株式会社", "2026-10-02", 1200, conf="medium", note="どちらが伝票番号か不明")
    # 6) 全角・斜め: 伝票「００４５６７」/ 一覧「4567」→ 一致
    slip_hokuto("００４５６７", "2026年10月3日", 5400).save(slips / "北斗化学.jpg", quality=88)
    mock["北斗化学.jpg"] = R(["００４５６７"], "北斗化学(株)", "2026-10-03", 5400, note="斜めだが読める")
    # 7) 手書き → 要確認（読めていても必ず人が見る）
    slip_handwritten("H-2210").save(slips / "丸山商会_手書き.png")
    mock["丸山商会_手書き.png"] = R(["H-2210"], "丸山商会", None, None, hw=True, conf="medium", note="手書き。2と7の判別に迷う")
    # 8) 複数ページPDF（大和電機）: 1枚目=一致 / 2枚目=一覧にない / 3枚目=一致（金額相違）
    pages = [slip_daiwa("DE-7001", 52000), slip_daiwa("DE-7002", 9800), slip_daiwa("DE-7003", 53000)]
    pages[0].save(slips / "大和電機_まとめ.pdf", save_all=True, append_images=pages[1:], resolution=150)
    mock["大和電機_まとめ.pdf#1"] = R(["DE-7001"], "大和電機", "2026-10-02", 52000)
    mock["大和電機_まとめ.pdf#2"] = R(["DE-7002"], "大和電機", "2026-10-02", 9800)
    mock["大和電機_まとめ.pdf#3"] = R(["DE-7003"], "大和電機", "2026-10-02", 53000)
    # 9) EXIFで横向き保存されたJPEG → 向き補正 → 一致
    with_exif_rotation(slip_simple("大阪精機", "納品書番号", "OS-20261005", 77000), slips / "大阪精機_横向き.jpg")
    mock["大阪精機_横向き.jpg"] = R(["OS-20261005"], "大阪精機", "2026-10-05", 77000)
    # 10) 不鮮明で読めない → 要確認（番号なし）
    slip_simple("三光産業", "伝票No.", "SK-3319").filter(ImageFilter.GaussianBlur(14)).save(slips / "三光産業_ぼやけ.jpg")
    mock["三光産業_ぼやけ.jpg"] = R([], "三光産業", None, None, conf="low", note="ぼやけて番号が判読できない")
    # 11) 読めたが自信度が低い → 要確認
    slip_simple("青葉工業", "No.", "AB-5521").filter(ImageFilter.GaussianBlur(3)).save(slips / "青葉工業_かすれ.png")
    mock["青葉工業_かすれ.png"] = R(["AB-5521"], "青葉工業", None, None, conf="low", note="かすれており5と6の区別が不確か")
    # 12) API障害（読み取り失敗）を再現 → 要確認（読み取り失敗）
    slip_simple("松本商事", "伝票No.", "MS-4410").save(slips / "松本商事_失敗.png")
    mock["松本商事_失敗.png"] = {"__error__": "API呼び出しに失敗: ConnectionError（模擬）"}
    # 13) 一覧にない（小林工業）
    slip_simple("小林工業", "納品書No.", "KS-9999", 4000).save(slips / "小林工業.png")
    mock["小林工業.png"] = R(["KS-9999"], "小林工業", "2026-10-05", 4000)
    # 14) 壊れた画像ファイル → 要確認（読み取り失敗）。モックでは画像を開かないので、実AIモードで効果がある
    (slips / "壊れたファイル.jpg").write_bytes(b"not an image")
    mock["壊れたファイル.jpg"] = R([], None, conf="low", note="（モック）")

    (slips / "_mock_readings.json").write_text(json.dumps(mock, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- 仕入一覧表 ---
    wb = Workbook()
    ws = wb.active
    ws.title = "仕入一覧"
    ws.append(["仕入日", "メーカー", "伝票番号", "金額", "備考"])
    D = lambda m, d: datetime(2026, m, d)
    rows = [
        (D(10, 1), "山田製作所", "2026-10-0001", 128000, ""),
        (D(10, 2), "東海部品", "TK-123", 33000, "表記ゆれ（先頭ゼロ）"),
        (D(10, 2), "東海部品", "TK-00124", 8800, ""),
        (D(10, 3), "北斗化学", 4567, 5400, "数値セル"),
        (D(10, 4), "丸山商会", "H2210", 15000, "手書き伝票"),
        (D(10, 2), "大和電機", "DE-7001", 52000, ""),
        (D(10, 2), "大和電機", "DE-7003", 52000, "伝票は53,000円"),
        (D(10, 5), "大阪精機", "OS-20261005", 77000, ""),
        (D(10, 4), "三光産業", "SK-3319", 21000, "伝票がぼやけている"),
        (D(10, 4), "青葉工業", "AB-5521", 6600, ""),
        (D(10, 5), "松本商事", "MS-4410", 3300, ""),
        (D(10, 5), "西村金属", "NM-0001", 18000, "伝票が来ていない"),
        (D(10, 5), "西村金属", "NM-0002", 2400, "伝票が来ていない"),
    ]
    for r in rows:
        ws.append(list(r))
    for row in ws.iter_rows(min_row=2, min_col=1, max_col=1):
        row[0].number_format = "yyyy/mm/dd"
    wb.save(out / "仕入一覧表.xlsx")
    return {"slips": slips, "ledger": out / "仕入一覧表.xlsx", "mock": mock}


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "sample_data"
    info = generate(target)
    print(f"生成しました: {info['slips']}  /  {info['ledger']}")
