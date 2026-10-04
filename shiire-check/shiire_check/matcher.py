"""照合ロジック（GUI非依存）。

方針: 読み取れない・自信がない・手書き・候補が特定できないものは、黙って「一致」にせず必ず「要確認」にする。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from shiire_check.normalize import (
    Normalizer, dates_close, makers_compatible, parse_amount, parse_date,
)
from shiire_check.schema import CONFIDENCE_JA, CONFIDENCE_RANK, ReadResult

MATCH, NO_SLIP, NOT_IN_LEDGER, REVIEW = "一致", "伝票なし", "一覧にない", "要確認"
CATEGORIES = [MATCH, NO_SLIP, NOT_IN_LEDGER, REVIEW]

W_AMOUNT, W_DATE, W_MAKER = "金額相違", "日付相違", "メーカー相違"
W_SLIP_DUP, W_LEDGER_DUP = "伝票番号重複", "一覧に重複"


@dataclass
class LedgerRow:
    row: int                      # Excel上の行番号
    number: str                   # 元の表記
    maker: str | None = None
    date: object = None           # date / datetime / str
    amount: object = None


@dataclass
class SlipInput:
    key: str
    name: str                     # 表示用ファイル名
    source_file: str
    result: ReadResult | None
    error: str | None = None
    override: str | None = None   # 手修正した伝票番号


@dataclass
class ResultRow:
    key: str
    category: str
    slip_number: str
    maker: str
    date: str
    note: str
    source_file: str
    confidence: str               # 高/中/低/""
    handwritten: bool = False
    is_slip: bool = True
    warnings: list[str] = field(default_factory=list)
    ledger_rows: list[int] = field(default_factory=list)
    confirmed: bool = False
    memo: str = ""

    @property
    def label(self) -> str:
        return self.category + (f"（{'・'.join(self.warnings)}）" if self.warnings else "")


def match(
    slips: list[SlipInput],
    ledger: list[LedgerRow],
    cfg: dict,
    norm: Normalizer,
    use_amount: bool = False,
    use_date: bool = False,
    use_maker: bool = False,
) -> list[ResultRow]:
    mcfg = cfg["matching"]
    min_rank = CONFIDENCE_RANK[mcfg["min_confidence"]]

    ledger_idx: dict[str, list[LedgerRow]] = {}
    for lr in ledger:
        n = norm(lr.number)
        if n:
            ledger_idx.setdefault(n, []).append(lr)

    # --- 1) 伝票ごとの候補と要確認判定 ---
    analyzed = []
    for s in slips:
        cands: dict[str, str] = {}          # 正規化 -> 元表記
        reasons: list[str] = []
        manual = bool(s.override and s.override.strip())
        if manual:
            n = norm(s.override)
            if n:
                cands[n] = s.override.strip()
        elif s.error:
            reasons.append(s.error if s.error.startswith("読み取り失敗") else f"読み取り失敗: {s.error}")
        elif s.result is not None:
            for raw in s.result.slip_numbers:
                n = norm(raw)
                if n and n not in cands:
                    cands[n] = raw
            if not cands:
                reasons.append("伝票番号を読み取れません")
            if CONFIDENCE_RANK[s.result.confidence] < min_rank:
                reasons.append(f"自信度が{CONFIDENCE_JA[s.result.confidence]}")
            if s.result.handwritten and mcfg["review_if_handwritten"]:
                reasons.append("手書き")
        else:
            reasons.append("読み取り失敗: 結果がありません")
        analyzed.append((s, cands, reasons, manual))

    # --- 2) 候補が複数のときの特定 ---
    chosen: dict[int, str | None] = {}      # 伝票の並び順 -> 正規化番号（特定できた場合）
    multi_note: dict[int, str] = {}
    for i, (s, cands, reasons, manual) in enumerate(analyzed):
        pick = None
        if len(cands) == 1:
            pick = next(iter(cands))
        elif len(cands) > 1:
            in_ledger = [n for n in cands if n in ledger_idx]
            if mcfg["multi_candidate_policy"] == "prefer_ledger" and len(in_ledger) == 1:
                pick = in_ledger[0]
                multi_note[i] = "候補が複数（" + " / ".join(cands.values()) + "）のうち一覧にあるものを採用"
            else:
                reasons.append("候補が複数で特定できません（" + " / ".join(cands.values()) + "）")
        chosen[i] = pick

    # --- 3) 伝票同士の重複 ---
    by_num: dict[str, list[SlipInput]] = {}
    for i, (s, cands, reasons, manual) in enumerate(analyzed):
        if chosen[i]:
            by_num.setdefault(chosen[i], []).append(s)

    claimed: set[str] = set()
    unreadable = 0
    rows: list[ResultRow] = []

    for i, (s, cands, reasons, manual) in enumerate(analyzed):
        res = s.result
        pick = chosen[i]
        shown = (cands[pick] if pick else " / ".join(cands.values())) if cands else ""
        warnings: list[str] = []
        notes: list[str] = []
        lrows: list[LedgerRow] = ledger_idx.get(pick, []) if pick else []

        if reasons:
            category = REVIEW
            notes = list(reasons)
            for n in cands:                     # 要確認でも、一覧側の対応行は「伝票なし」にしない
                if n in ledger_idx:
                    claimed.add(n)
            if not cands:
                unreadable += 1
            if pick:
                notes.append("一覧に該当あり" if lrows else "一覧に該当なし")
        elif lrows:
            category = MATCH
            claimed.add(pick)
        else:
            category = NOT_IN_LEDGER
            notes.append("仕入一覧表にこの番号がありません")

        if manual:
            notes.insert(0, "手修正済み")
        if i in multi_note and not reasons:
            notes.append(multi_note[i])

        # 補助照合（番号が一致した行に対して）
        if lrows and pick:
            if use_amount and res and res.total_amount is not None:
                amts = [parse_amount(l.amount) for l in lrows if parse_amount(l.amount) is not None]
                tol = float(mcfg["amount_tolerance"])
                if amts and not any(abs(a - res.total_amount) <= tol for a in amts):
                    warnings.append(W_AMOUNT)
                    notes.append(f"金額 伝票{res.total_amount:,.0f}円 / 一覧{amts[0]:,.0f}円")
            if use_date and res and parse_date(res.date):
                ds = [parse_date(l.date) for l in lrows if parse_date(l.date)]
                if ds and not any(dates_close(parse_date(res.date), d, int(mcfg["date_tolerance_days"])) for d in ds):
                    warnings.append(W_DATE)
                    notes.append(f"日付 伝票{parse_date(res.date)} / 一覧{ds[0]}")
            if use_maker and res and res.maker:
                ms = [l.maker for l in lrows if l.maker]
                if ms and not any(makers_compatible(res.maker, m) for m in ms):
                    warnings.append(W_MAKER)
                    notes.append(f"メーカー 伝票「{res.maker}」/ 一覧「{ms[0]}」")
            if len(lrows) > 1:
                warnings.append(W_LEDGER_DUP)
                notes.append("仕入一覧の行 " + ",".join(str(l.row) for l in lrows))
        if pick and len(by_num[pick]) > 1:
            warnings.append(W_SLIP_DUP)
            others = [o.name for o in by_num[pick] if o is not s]
            notes.append("同じ番号の伝票: " + ", ".join(others))

        rows.append(ResultRow(
            key=s.key, category=category, slip_number=shown,
            maker=(res.maker or "") if res else "",
            date=(res.date or "") if res else "",
            note="；".join(notes) + (f"｜AIメモ: {res.note}" if res and res.note else ""),
            source_file=s.name,
            confidence="" if (manual or not res) else CONFIDENCE_JA[res.confidence],
            handwritten=bool(res and res.handwritten),
            warnings=warnings,
            ledger_rows=[l.row for l in lrows],
        ))

    # --- 4) 伝票のない一覧行 ---
    occurrence: dict[str, int] = {}
    for lr in ledger:
        n = norm(lr.number)
        if not n or n in claimed:
            continue
        i = occurrence[n] = occurrence.get(n, 0) + 1
        warnings = [W_LEDGER_DUP] if len(ledger_idx[n]) > 1 else []
        note = f"仕入一覧 {lr.row}行目"
        if unreadable:
            note += f"（読み取れなかった伝票が{unreadable}枚あります。該当するか確認してください）"
        d = parse_date(lr.date)
        rows.append(ResultRow(
            key=f"ledger:{n}#{i}", category=NO_SLIP, slip_number=lr.number,
            maker=lr.maker or "", date=d.isoformat() if d else (str(lr.date) if lr.date else ""),
            note=note, source_file="", confidence="", is_slip=False,
            warnings=warnings, ledger_rows=[lr.row],
        ))
    return rows


def summarize(rows: list[ResultRow]) -> dict[str, int]:
    out = {c: 0 for c in CATEGORIES}
    for r in rows:
        out[r.category] += 1
    return out
