"""座標ベースの運賃表PDFパーサー。

テキスト抽出順は信用せず、pdfplumber の単語座標から
  - サイズ見出し行 → 列の x 座標
  - 地帯ラベル → 行の y 座標
  - 数値セル → 最も近い (行, 列) に割り当て
で復元する。レイアウト差異は config/parser.yaml の profile で調整する。

機密保持: 例外・警告・ログには運賃表の中身を含めない（種別と構造情報のみ）。
"""
from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field

import pdfplumber

from .config import Settings

log = logging.getLogger("fare_hub.parser")
logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pdfplumber").setLevel(logging.ERROR)

PRICE_RE = re.compile(r"^[¥￥]?(\d{1,3}(?:,\d{3})+|\d+)円?$")
SIZE_RE = re.compile(r"^(\d{2,3})(?:サイズ|cm|size)?$", re.I)
WEIGHT_RE = re.compile(r"^(\d+(?:\.\d+)?)kg$", re.I)
DATE_RE = re.compile(r"(令和|R)?(\d{1,4})[年/\-.](\d{1,2})[月/\-.](\d{1,2})日?")
BULLET_RE = re.compile(r"^([※・●■▪◆*＊\-]|\d+[.．)）]|注\d*[:：]?)")
MAX_PRICE = 1_000_000


class ParseError(Exception):
    """致命的なパース失敗。kind は短い種別コード（内容は含めない）。"""

    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


@dataclass
class ParseResult:
    profile: str = ""
    header: dict[str, str] = field(default_factory=dict)
    rates: dict[tuple[str, int], int] = field(default_factory=dict)
    weights: dict[int, float] = field(default_factory=dict)
    notes: list[tuple[str, str]] = field(default_factory=list)  # (category, text)
    warnings: list[dict] = field(default_factory=list)  # {kind, detail}（内容は含めない）

    @property
    def score(self) -> int:
        return len(self.rates) * 10 + len(self.header) * 3 + len(self.weights)


def _cond(s: str) -> str:
    return "".join(s.split())


def _cy(w: dict) -> float:
    return (w["top"] + w["bottom"]) / 2


def _cx(w: dict) -> float:
    return (w["x0"] + w["x1"]) / 2


def group_lines(words: list[dict], tol: float) -> list[list[dict]]:
    lines: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (_cy(w), w["x0"])):
        if lines and abs(_cy(w) - sum(_cy(x) for x in lines[-1]) / len(lines[-1])) <= tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(l, key=lambda w: w["x0"]) for l in lines]


def _join(words: list[dict]) -> str:
    out = ""
    for w in words:
        t = w["text"]
        if out and out[-1].isascii() and out[-1].isalnum() and t[0].isascii() and t[0].isalnum():
            out += " "
        out += t
    return out


def parse_date(text: str) -> str | None:
    m = DATE_RE.search(text)
    if not m:
        return None
    era, y, mo, d = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
    if era:
        y += 2018
    if not (1 <= mo <= 12 and 1 <= d <= 31 and 1900 <= y <= 2200):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


# ---------------------------------------------------------------- ヘッダー
def _parse_header(lines: list[list[dict]], profile: dict) -> dict[str, str]:
    labels: list[tuple[str, str]] = []  # (condensed label, field)
    for fld, cands in profile["header_fields"].items():
        labels += [(_cond(c), fld) for c in cands]
    header: dict[str, str] = {}
    gap = profile.get("header_gap")
    segments: list[list[dict]] = []
    for line in lines:
        if not gap:
            segments.append(line)
            continue
        seg = [line[0]]
        for w in line[1:]:
            if w["x0"] - seg[-1]["x1"] > gap:
                segments.append(seg)
                seg = []
            seg.append(w)
        segments.append(seg)
    for line in segments:
        text = _cond(_join(line))
        hits = []
        for lab, fld in labels:
            i = text.find(lab)
            while i >= 0:
                hits.append((i, -len(lab), i + len(lab), fld))
                i = text.find(lab, i + 1)
        hits.sort()
        kept, end = [], -1
        for start, _, stop, fld in hits:  # 重なるラベルは長い方を優先
            if start >= end:
                kept.append((start, stop, fld))
                end = stop
        for k, (_, stop, fld) in enumerate(kept):
            nxt = kept[k + 1][0] if k + 1 < len(kept) else len(text)
            val = text[stop:nxt].strip(":：　 ")
            if val and fld not in header:
                header[fld] = val
    return header


# ---------------------------------------------------------------- マトリクス
def _find_size_header(lines, sizes, min_n):
    for li, line in enumerate(lines):
        found = {}
        for w in line:
            m = SIZE_RE.match(w["text"])
            if m and int(m.group(1)) in sizes and int(m.group(1)) not in found:
                found[int(m.group(1))] = w
        if len(found) >= min_n:
            return li, found
    return None


def _parse_matrix(words, st: Settings, profile: dict, res: ParseResult):
    """1ページ分。戻り値: (見出し行index, 最終行の縦座標, lines) / マトリクス無しなら None。"""
    mcfg = profile["matrix"]
    lines = group_lines(words, mcfg["line_tol"])
    hdr = _find_size_header(lines, set(st.sizes), mcfg["min_size_headers"])
    if not hdr:
        return None
    li, size_words = hdr
    cols = {s: _cx(w) for s, w in size_words.items()}
    xs = sorted(cols.values())
    gap = min(b - a for a, b in zip(xs, xs[1:])) if len(xs) > 1 else 40
    hdr_y = _cy(size_words[next(iter(size_words))])
    hdr_ids = {id(w) for w in lines[li]}

    def col_of(x: float) -> int | None:
        s, cx = min(cols.items(), key=lambda kv: abs(kv[1] - x))
        return s if abs(cx - x) <= gap / 2 else None

    # 重量目安（見出し直下）
    for w in words:
        m = WEIGHT_RE.match(w["text"])
        if m and 0 < _cy(w) - hdr_y < 30 and (s := col_of(_cx(w))) is not None:
            res.weights[s] = float(m.group(1))

    # 地帯ラベル（正式名/別名の完全一致。同名が複数あれば最も左を採用）
    lookup = st.region_lookup()
    left_limit = xs[0] - gap / 2
    rows: dict[str, float] = {}
    for w in sorted(words, key=lambda w: w["x0"]):
        name = lookup.get(_cond(w["text"]))
        if name and name not in rows and w["x1"] <= left_limit and _cy(w) > hdr_y + 2:
            rows[name] = _cy(w)
    for r in st.region_names:
        if r not in rows:
            res.warnings.append({"kind": "region_not_found", "detail": r})

    # 価格セル
    seen: dict[tuple[str, int], int] = {}
    dup: set[tuple[str, int]] = set()
    for w in words:
        if id(w) in hdr_ids or _cy(w) <= hdr_y + 2:
            continue
        m = PRICE_RE.match(w["text"])
        if not m or not rows:
            continue
        region, dy = min(((r, abs(_cy(w) - y)) for r, y in rows.items()), key=lambda t: t[1])
        s = col_of(_cx(w))
        if dy > mcfg["row_tol"] or s is None:
            continue
        price = int(m.group(1).replace(",", ""))
        if not 1 <= price <= MAX_PRICE:
            res.warnings.append({"kind": "price_out_of_range", "detail": f"{region}/{s}"})
            continue
        key = (region, s)
        if key in seen:
            dup.add(key)
        else:
            seen[key] = price
    for key in dup:
        seen.pop(key, None)
        res.warnings.append({"kind": "duplicate_cell", "detail": f"{key[0]}/{key[1]}"})
    for key, price in seen.items():
        res.rates.setdefault(key, price)

    for s in st.sizes:
        if s not in cols:
            res.warnings.append({"kind": "size_header_missing", "detail": str(s)})
    return li, (max(rows.values()) if rows else hdr_y), lines


def _parse_matrix_transposed(words, st: Settings, profile: dict, res: ParseResult):
    """行=サイズ・列=地帯のレイアウト。字間をあけた地帯名は列のx座標でまとめて照合する。"""
    mcfg = profile["matrix"]
    lines = group_lines(words, mcfg["line_tol"])
    nreg = len(st.region_names)
    price_like = lambda l: [w for w in l if PRICE_RE.match(w["text"])]

    li = next((i for i, l in enumerate(lines) if len(price_like(l)) >= nreg), None)
    if li is None:
        return None
    first = sorted(price_like(lines[li]), key=lambda w: w["x0"])[-nreg:]  # 右端の nreg 個が地帯の列
    cols = [_cx(w) for w in first]
    gap = min(b - a for a, b in zip(cols, cols[1:]))
    left_limit = cols[0] - gap / 2

    def col_of(x: float) -> int | None:
        c = min(range(nreg), key=lambda i: abs(cols[i] - x))
        return c if abs(cols[c] - x) <= gap / 2 else None

    # 列 -> 地帯（見出し行を上から見て、列ごとに結合した文字列が地帯名/別名に一致する最初のもの）
    lookup = st.region_lookup()
    col_region: dict[int, str] = {}
    for line in lines[:li]:
        by_col: dict[int, list[dict]] = {}
        for w in line:
            c = col_of(_cx(w))
            if c is not None:
                by_col.setdefault(c, []).append(w)
        for c, ws in by_col.items():
            name = lookup.get(_cond("".join(w["text"] for w in sorted(ws, key=lambda w: w["x0"]))))
            if name and c not in col_region and name not in col_region.values():
                col_region[c] = name
    if len(col_region) < mcfg["min_size_headers"]:
        return None
    for r in st.region_names:
        if r not in col_region.values():
            res.warnings.append({"kind": "region_not_found", "detail": r})

    # データ行: 左端にサイズ、重量目安、列位置に運賃
    kg = re.compile(r"(\d+(?:\.\d+)?)\s*kg", re.I)
    seen: dict[tuple[str, int], int] = {}
    dup: set[tuple[str, int]] = set()
    sizes_found: set[int] = set()
    last_y = _cy(lines[li][0])
    for line in lines[li:]:
        left = [w for w in line if _cx(w) < left_limit]
        size = next((int(m.group(1)) for w in left if (m := SIZE_RE.match(w["text"])) and int(m.group(1)) in st.sizes), None)
        if size is None:
            continue
        sizes_found.add(size)
        last_y = max(last_y, _cy(line[0]))
        for w in left:
            if m := kg.search(w["text"]):
                res.weights[size] = float(m.group(1))
        for w in line:
            c = col_of(_cx(w)) if _cx(w) >= left_limit else None
            m = PRICE_RE.match(w["text"])
            if c is None or not m or c not in col_region:
                continue
            price = int(m.group(1).replace(",", ""))
            key = (col_region[c], size)
            if not 1 <= price <= MAX_PRICE:
                res.warnings.append({"kind": "price_out_of_range", "detail": f"{key[0]}/{size}"})
            elif key in seen:
                dup.add(key)
            else:
                seen[key] = price
    for key in dup:
        seen.pop(key, None)
        res.warnings.append({"kind": "duplicate_cell", "detail": f"{key[0]}/{key[1]}"})
    for key, price in seen.items():
        res.rates.setdefault(key, price)
    for s in st.sizes:
        if s not in sizes_found:
            res.warnings.append({"kind": "size_header_missing", "detail": str(s)})
    return li, last_y, lines


# ---------------------------------------------------------------- 注記
def _classify(text: str, categories: list[dict]) -> str:
    for c in categories:
        if any(k in text for k in c["keywords"]):
            return c["key"]
    return "other"


def _parse_notes(lines, bottom: float, cfg: dict) -> list[tuple[str, str]]:
    ignore = [re.compile(p) for p in cfg.get("ignore_patterns", [])]
    heads = {_cond(h) for h in cfg.get("headings", [])}
    notes: list[str] = []
    for line in lines:
        if sum(_cy(w) for w in line) / len(line) <= bottom + 6:
            continue
        text = _join(line).strip()
        if not text or _cond(text) in heads or any(p.search(text) for p in ignore):
            continue
        if not notes or BULLET_RE.match(text):
            notes.append(text)
        else:
            notes[-1] += text
    return [(_classify(n, cfg["categories"]), n) for n in notes]


# ---------------------------------------------------------------- 入口
def _parse_with_profile(pages_words, st: Settings, profile: dict) -> ParseResult:
    res = ParseResult(profile=profile["name"])
    found_matrix = False
    parse = _parse_matrix_transposed if profile.get("orientation") == "transposed" else _parse_matrix
    for words in pages_words:
        out = parse(words, st, profile, res)
        if out is None:
            continue
        found_matrix = True
        li, bottom, lines = out
        if not res.header:
            res.header = _parse_header(lines[:li], profile)
        res.notes += _parse_notes(lines, bottom, st.parser["notes"])
    if not found_matrix:
        raise ParseError("size_header_not_found")
    return res


def _validate(res: ParseResult, st: Settings) -> None:
    for f in ("origin", "valid_from", "valid_to"):
        if f not in res.header:
            res.warnings.append({"kind": "header_missing", "detail": f})
    for f in ("valid_from", "valid_to"):
        if f in res.header:
            iso = parse_date(res.header[f])
            if iso:
                res.header[f] = iso
            else:
                res.warnings.append({"kind": "header_invalid", "detail": f})
                del res.header[f]
    vf, vt = res.header.get("valid_from"), res.header.get("valid_to")
    if vf and vt and vf > vt:
        res.warnings.append({"kind": "date_order", "detail": "valid_from>valid_to"})
    for s in st.weight_sizes:
        if s not in res.weights:
            res.warnings.append({"kind": "weight_missing", "detail": str(s)})
    if not res.notes:
        res.warnings.append({"kind": "notes_missing", "detail": ""})


def parse_pdf(data: bytes, st: Settings) -> ParseResult:
    limits = st.parser["limits"]
    if len(data) > limits["max_file_mb"] * 1024 * 1024:
        raise ParseError("file_too_large")
    if not data.startswith(b"%PDF"):
        raise ParseError("not_a_pdf")
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages) > limits["max_pages"]:
                raise ParseError("too_many_pages")
            # 字間をあけた文字（地帯名・日付）に対応するため、profile ごとに単語化の許容差を変える
            tols = {float(pr.get("word_x_tol", 1.5)) for pr in st.parser["profiles"]}
            words_by_tol = {t: [p.extract_words(x_tolerance=t, y_tolerance=2) for p in pdf.pages] for t in tols}
    except ParseError:
        raise
    except Exception as e:  # 例外メッセージには中身が含まれうるので型名のみ
        raise ParseError(f"pdf_open_failed:{type(e).__name__}") from None
    if not any(any(pw) for pw in words_by_tol.values()):
        raise ParseError("no_text_layer")  # スキャンPDF等（OCR対象外）

    best: ParseResult | None = None
    for profile in st.parser["profiles"]:
        try:
            r = _parse_with_profile(words_by_tol[float(profile.get("word_x_tol", 1.5))], st, profile)
        except ParseError:
            continue
        if best is None or r.score > best.score:
            best = r
    if best is None:
        raise ParseError("size_header_not_found")
    _validate(best, st)
    return best
