from datetime import datetime

import pytest

from shiire_check.matcher import (
    LedgerRow, SlipInput, match, summarize,
    MATCH, NO_SLIP, NOT_IN_LEDGER, REVIEW,
)
from shiire_check.normalize import Normalizer
from shiire_check.schema import ReadResult


def rr(nums, conf="high", hw=False, maker=None, date=None, amount=None, note=""):
    return ReadResult(slip_numbers=nums, handwritten=hw, confidence=conf, maker=maker,
                      date=date, total_amount=amount, note=note)


def slip(name, result=None, error=None, override=None, key=None):
    return SlipInput(key or name, name, name, result, error, override)


def run(slips, ledger, cfg, **kw):
    return match(slips, ledger, cfg, Normalizer(cfg["normalize"]), **kw)


def by(rows, name):
    return next(r for r in rows if r.source_file == name)


L = lambda row, no, **kw: LedgerRow(row, no, **kw)


def test_four_categories(cfg):
    rows = run(
        [slip("a", rr(["100"])), slip("b", rr(["999"])), slip("c", rr([], conf="low"))],
        [L(2, "100"), L(3, "200")], cfg)
    assert by(rows, "a").category == MATCH
    assert by(rows, "b").category == NOT_IN_LEDGER
    assert by(rows, "c").category == REVIEW
    ledger_only = [r for r in rows if not r.is_slip]
    assert [(r.category, r.slip_number) for r in ledger_only] == [(NO_SLIP, "200")]
    assert summarize(rows) == {MATCH: 1, NO_SLIP: 1, NOT_IN_LEDGER: 1, REVIEW: 1}


def test_notation_variants_match(cfg):
    rows = run([slip("a", rr(["００４５６７"])), slip("b", rr(["TK-00123"])), slip("c", rr(["ab 12-3"]))],
               [L(2, "4567"), L(3, "TK-123"), L(4, "AB123")], cfg)
    assert [r.category for r in rows] == [MATCH] * 3


@pytest.mark.parametrize("result,reason,claims_ledger", [
    (rr(["100"], conf="low"), "自信度", True),
    (rr(["100"], hw=True), "手書き", True),
    (rr([]), "読み取れません", False),
])
def test_never_silently_match(cfg, result, reason, claims_ledger):
    """読めない・自信がない・手書きは、一覧に番号があっても「一致」にしない。"""
    rows = run([slip("a", result)], [L(2, "100")], cfg)
    r = by(rows, "a")
    assert r.category == REVIEW and reason in r.note
    # 番号が読めている場合、対応する一覧行は「伝票なし」にしない。読めない場合は残し、注記で知らせる
    assert (len(rows) == 1) == claims_ledger


def test_medium_confidence_threshold_configurable(cfg):
    ledger = [L(2, "100")]
    assert by(run([slip("a", rr(["100"], conf="medium"))], ledger, cfg), "a").category == MATCH
    cfg["matching"]["min_confidence"] = "high"
    assert by(run([slip("a", rr(["100"], conf="medium"))], ledger, cfg), "a").category == REVIEW


def test_handwritten_can_be_allowed_by_config(cfg):
    cfg["matching"]["review_if_handwritten"] = False
    assert by(run([slip("a", rr(["100"], hw=True))], [L(2, "100")], cfg), "a").category == MATCH


def test_read_failure_is_review_and_run_continues(cfg):
    rows = run([slip("bad", None, error="API呼び出しに失敗: timeout"), slip("ok", rr(["100"]))],
               [L(2, "100")], cfg)
    assert by(rows, "bad").category == REVIEW
    assert "読み取り失敗" in by(rows, "bad").note
    assert by(rows, "ok").category == MATCH


def test_unreadable_slips_are_mentioned_on_no_slip_rows(cfg):
    rows = run([slip("bad", None, error="x")], [L(2, "100")], cfg)
    ns = [r for r in rows if r.category == NO_SLIP][0]
    assert "読み取れなかった伝票が1枚" in ns.note


def test_multiple_candidates(cfg):
    ledger = [L(2, "TK-124")]
    # 一覧に存在する候補がちょうど1つ → 採用（注記つき）
    r = by(run([slip("a", rr(["TK-124", "NK-9001"]))], ledger, cfg), "a")
    assert r.category == MATCH and "候補が複数" in r.note and r.slip_number == "TK-124"
    # どれも一覧にない → 特定できず要確認
    r = by(run([slip("a", rr(["ZZ-1", "ZZ-2"]))], ledger, cfg), "a")
    assert r.category == REVIEW and "特定できません" in r.note
    # 両方一覧にある → 特定できず要確認、両方の一覧行は「伝票なし」にしない
    rows = run([slip("a", rr(["A1", "B2"]))], [L(2, "A1"), L(3, "B2")], cfg)
    assert by(rows, "a").category == REVIEW and len(rows) == 1
    # 方針をreviewにすると常に要確認
    cfg["matching"]["multi_candidate_policy"] = "review"
    assert by(run([slip("a", rr(["TK-124", "NK-9001"]))], ledger, cfg), "a").category == REVIEW


def test_duplicate_slips_warn(cfg):
    rows = run([slip("a", rr(["100"])), slip("b", rr(["0100"]))], [L(2, "100")], cfg)
    for name, other in (("a", "b"), ("b", "a")):
        r = by(rows, name)
        assert r.category == MATCH and "伝票番号重複" in r.warnings and other in r.note
        assert "（伝票番号重複）" in r.label


def test_duplicate_slips_same_content_do_not_collide(cfg):
    rows = run([slip("a", rr(["100"]), key="same"), slip("b", rr(["100"]), key="same")], [L(2, "100")], cfg)
    assert all("伝票番号重複" in r.warnings for r in rows)


def test_duplicate_in_ledger_warns(cfg):
    rows = run([slip("a", rr(["100"]))], [L(2, "100"), L(5, "100")], cfg)
    r = by(rows, "a")
    assert r.category == MATCH and "一覧に重複" in r.warnings and "2,5" in r.note
    assert len(rows) == 1
    rows = run([], [L(2, "100"), L(5, "100")], cfg)
    assert len(rows) == 2 and all("一覧に重複" in r.warnings for r in rows)
    assert len({r.key for r in rows}) == 2


def test_amount_mismatch_warning(cfg):
    ledger = [L(2, "100", amount=12000)]
    r = by(run([slip("a", rr(["100"], amount=13000))], ledger, cfg, use_amount=True), "a")
    assert r.category == MATCH and r.warnings == ["金額相違"] and r.label == "一致（金額相違）"
    assert "13,000" in r.note and "12,000" in r.note
    # 金額列を指定していなければ比較しない
    assert by(run([slip("a", rr(["100"], amount=13000))], ledger, cfg), "a").warnings == []
    # 一致・文字列金額・許容差
    assert by(run([slip("a", rr(["100"], amount=12000))], [L(2, "100", amount="¥12,000")], cfg,
                   use_amount=True), "a").warnings == []
    cfg["matching"]["amount_tolerance"] = 1000
    assert by(run([slip("a", rr(["100"], amount=13000))], ledger, cfg, use_amount=True), "a").warnings == []
    # 伝票側の金額が読めていなければ警告しない（黙って一致でなく、そもそも番号は一致している）
    assert by(run([slip("a", rr(["100"]))], ledger, cfg, use_amount=True), "a").warnings == []


def test_date_and_maker_mismatch_warning(cfg):
    ledger = [L(2, "100", maker="山田製作所", date=datetime(2026, 10, 1))]
    r = by(run([slip("a", rr(["100"], maker="東海部品", date="2026-10-03"))], ledger, cfg,
               use_date=True, use_maker=True), "a")
    assert set(r.warnings) == {"日付相違", "メーカー相違"}
    r = by(run([slip("a", rr(["100"], maker="山田製作所(株)", date="2026年10月1日"))], ledger, cfg,
               use_date=True, use_maker=True), "a")
    assert r.warnings == []
    cfg["matching"]["date_tolerance_days"] = 2
    r = by(run([slip("a", rr(["100"], date="2026-10-03"))], ledger, cfg, use_date=True), "a")
    assert r.warnings == []


def test_manual_correction_rematches(cfg):
    ledger = [L(2, "5521")]
    s = slip("a", rr(["5527"], conf="low"))
    assert by(run([s], ledger, cfg), "a").category == REVIEW
    s.override = "5521"      # 人が目で見て修正
    r = by(run([s], ledger, cfg), "a")
    assert r.category == MATCH and "手修正済み" in r.note
    s.override = "7777"      # 修正した番号が一覧にない
    assert by(run([s], ledger, cfg), "a").category == NOT_IN_LEDGER


def test_manual_correction_fixes_read_failure(cfg):
    s = slip("a", None, error="timeout", override="100")
    assert by(run([s], [L(2, "100")], cfg), "a").category == MATCH


def test_blank_ledger_numbers_ignored(cfg):
    rows = run([], [L(2, ""), L(3, "  - ")], cfg)
    assert rows == []
