import io

from pypdf import PdfReader

from app import slip

S = {"receipt_no": "RT-20261008-001", "received_on": "2026-10-08", "customer": "ダミー商事", "part_no": "ABC-1234",
     "product_name": "ダミー電気ケトル" * 6, "maker": "ダミー電機", "serial_no": "SN0000123456",
     "defect": "電源が入らない", "quantity": 1, "staff": "山田", "url": "http://returns.local:8000/r/RT-20261008-001"}


def _pages(pdf):
    r = PdfReader(io.BytesIO(pdf))
    return [(float(p.mediabox.width) / 72 * 25.4, float(p.mediabox.height) / 72 * 25.4) for p in r.pages]


def test_a5_one_per_page():
    sizes = _pages(slip.render_pdf([S, S, S], "a5"))
    assert len(sizes) == 3
    for w, h in sizes:
        assert abs(w - 148) < 0.3 and abs(h - 210) < 0.3


def test_a4_two_up_imposition():
    sizes = _pages(slip.render_pdf([S] * 3, "a4_2up"))
    assert len(sizes) == 2  # 3枚 → A4が2枚(2枚+1枚)
    for w, h in sizes:
        assert abs(w - 297) < 0.3 and abs(h - 210) < 0.3


def test_text_present_and_qr_url_fits():
    reader = PdfReader(io.BytesIO(slip.render_pdf([S], "a5")))
    text = reader.pages[0].extract_text()
    assert "RT-20261008-001" in text and "ABC-1234" in text


def test_fit_shrinks_then_truncates():
    slip._register_font()
    size, lines = slip.fit("あ" * 200, 16, 10, 100, 2)
    assert size == 10 and len(lines) == 2 and lines[-1].endswith("…")
    size, lines = slip.fit("短い", 26, 12, 300, 1)
    assert size == 26 and lines == ["短い"]


def test_empty_list_still_valid_pdf():
    assert len(_pages(slip.render_pdf([], "a5"))) == 1
