from types import SimpleNamespace

import pytest

from shiire_check.cache import Cache
from shiire_check.imaging import collect_pages, prepare_for_api, render_page
from shiire_check.pipeline import Cancelled, read_all
from shiire_check.reader import ClaudeReader, MockReader, ReaderError, parse_response
from shiire_check.schema import ReadResult
import threading

GOOD = {"slip_numbers": [" A-1 ", "A-1", ""], "handwritten": False, "confidence": "high",
        "note": "ok", "total_amount": "¥1,200", "maker": " "}


def tool_resp(inp):
    return SimpleNamespace(content=[SimpleNamespace(type="tool_use", name="report_slip", input=inp)])


class FakeClient:
    def __init__(self, behavior):
        self.messages = SimpleNamespace(create=behavior)


def reader_with(behavior, cfg):
    return ClaudeReader(cfg, client=FakeClient(behavior))


def test_schema_validation_and_cleanup():
    r = parse_response(tool_resp(GOOD))
    assert r.slip_numbers == ["A-1"] and r.total_amount == 1200 and r.maker is None


@pytest.mark.parametrize("bad", [
    {"slip_numbers": ["1"], "handwritten": False, "confidence": "very high"},   # 列挙外
    {"slip_numbers": ["1"], "confidence": "high"},                               # 必須項目なし
    {"slip_numbers": ["1"], "handwritten": "maybe", "confidence": "high"},
])
def test_invalid_output_raises(bad):
    with pytest.raises(ReaderError):
        parse_response(tool_resp(bad))


def test_no_tool_use_raises():
    with pytest.raises(ReaderError):
        parse_response(SimpleNamespace(content=[SimpleNamespace(type="text", text="hi")]))


def test_request_shape(cfg, dummy):
    seen = {}

    def create(**kw):
        seen.update(kw)
        return tool_resp(GOOD)

    ref = collect_pages(dummy["slips"])[0]
    reader_with(create, cfg).read(ref, lambda: b"\xff\xd8jpeg")
    assert seen["model"] == cfg["model"]
    assert seen["tool_choice"] == {"type": "tool", "name": "report_slip"}
    assert seen["messages"][0]["content"][0]["type"] == "image"


def test_pipeline_survives_api_failures(cfg, dummy, tmp_path):
    calls = []

    def create(**kw):
        calls.append(1)
        if len(calls) % 2 == 0:
            raise ConnectionError("network down")
        return tool_resp(GOOD)

    pages = collect_pages(dummy["slips"])
    progress = []
    out = read_all(pages, reader_with(create, cfg), Cache(tmp_path / "c.db"), cfg,
                   progress=lambda d, t: progress.append((d, t)))
    assert len(out) == len(pages) == 16          # 14ファイル（PDFは3ページ）
    errs = [o for o in out if o.error]
    assert errs and all(o.result is None for o in errs)
    assert any("ConnectionError" in o.error for o in errs)
    assert any("PDFを開けません" in o.error or "読み取り失敗" in o.error for o in errs)
    assert progress[-1] == (16, 16)


def test_corrupt_file_becomes_error_not_crash(cfg, dummy, tmp_path):
    reader = reader_with(lambda **kw: tool_resp(GOOD), cfg)
    out = read_all(collect_pages(dummy["slips"]), reader, None, cfg)
    broken = next(o for o in out if o.ref.name == "壊れたファイル.jpg")
    assert broken.error and "読み取り失敗" in broken.error
    ok = next(o for o in out if o.ref.name == "北斗化学.jpg")
    assert ok.result is not None and ok.error is None


def test_cache_prevents_rereading(cfg, dummy, tmp_path):
    n = []

    def create(**kw):
        n.append(1)
        return tool_resp(GOOD)

    cache = Cache(tmp_path / "c.db")
    pages = [p for p in collect_pages(dummy["slips"]) if p.name == "北斗化学.jpg"]
    reader = reader_with(create, cfg)
    first = read_all(pages, reader, cache, cfg)
    second = read_all(pages, reader, cache, cfg)
    assert len(n) == 1 and not first[0].from_cache and second[0].from_cache


def test_failures_are_not_cached(cfg, dummy, tmp_path):
    cache = Cache(tmp_path / "c.db")
    pages = [p for p in collect_pages(dummy["slips"]) if p.name == "北斗化学.jpg"]
    bad = reader_with(lambda **kw: (_ for _ in ()).throw(TimeoutError("t")), cfg)
    assert read_all(pages, bad, cache, cfg)[0].error
    good = reader_with(lambda **kw: tool_resp(GOOD), cfg)
    assert read_all(pages, good, cache, cfg)[0].result is not None


def test_cancel(cfg, dummy):
    ev = threading.Event()
    ev.set()
    with pytest.raises(Cancelled):
        read_all(collect_pages(dummy["slips"]), MockReader(dummy["slips"]), None, cfg, cancel=ev)


def test_pdf_split_and_image_prep(cfg, dummy):
    pages = collect_pages(dummy["slips"])
    pdf = [p for p in pages if p.name == "大和電機_まとめ.pdf"]
    assert [p.page for p in pdf] == [1, 2, 3] and all(p.pages_total == 3 for p in pdf)
    assert len({p.key for p in pdf}) == 3
    # 長辺の縮小
    import io
    from PIL import Image
    big = next(p for p in pages if p.name == "山田製作所_001.jpg")
    jpeg = prepare_for_api(big, max_long_edge=800)
    assert max(Image.open(io.BytesIO(jpeg)).size) == 800
    # EXIFの向き補正: 横倒しで保存された画像が縦(元の向き)に戻る
    exif = next(p for p in pages if p.name == "大阪精機_横向き.jpg")
    w, h = render_page(exif).size
    assert w > h        # 元は横長(1000x700)の伝票
    assert Image.open(exif.path).size[0] < Image.open(exif.path).size[1]   # 保存画素は縦長


def test_mock_reader(dummy):
    m = MockReader(dummy["slips"])
    pages = collect_pages(dummy["slips"])
    ref = next(p for p in pages if p.name == "大和電機_まとめ.pdf" and p.page == 2)
    assert m.read(ref, lambda: b"").slip_numbers == ["DE-7002"]
    fail = next(p for p in pages if p.name == "松本商事_失敗.png")
    with pytest.raises(ReaderError):
        m.read(fail, lambda: b"")
