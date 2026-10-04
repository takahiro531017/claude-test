"""AIの読み取り結果のスキーマ（pydanticで検証）。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from shiire_check.normalize import parse_amount

CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
CONFIDENCE_JA = {"high": "高", "medium": "中", "low": "低"}


class ReadResult(BaseModel):
    slip_numbers: list[str] = Field(default_factory=list)
    maker: str | None = None
    date: str | None = None
    total_amount: float | None = None
    handwritten: bool
    confidence: Literal["high", "medium", "low"]
    note: str = ""

    @field_validator("slip_numbers", mode="before")
    @classmethod
    def _clean_numbers(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        out: list[str] = []
        for x in v:
            s = str(x).strip()
            if s and s not in out:
                out.append(s)
        return out[:10]

    @field_validator("maker", "date", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    @field_validator("total_amount", mode="before")
    @classmethod
    def _amount(cls, v):
        return parse_amount(v)

    @field_validator("note", mode="before")
    @classmethod
    def _note(cls, v):
        return "" if v is None else str(v)[:300]


# Claudeに強制的に呼ばせるツール（= 厳密なJSON出力）の入力スキーマ
TOOL_NAME = "report_slip"
TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": "読み取った伝票の内容を報告する。",
    "input_schema": {
        "type": "object",
        "properties": {
            "slip_numbers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "伝票番号（納品書番号・伝票No.等）の候補。見えたとおりの文字列。読み取れなければ空配列。",
            },
            "maker": {"type": ["string", "null"], "description": "発行元（メーカー・仕入先）の名称。不明ならnull。"},
            "date": {"type": ["string", "null"], "description": "伝票の日付。YYYY-MM-DD形式。不明ならnull。"},
            "total_amount": {"type": ["number", "null"], "description": "合計金額（税込があれば税込）。不明ならnull。"},
            "handwritten": {"type": "boolean", "description": "伝票番号が手書きならtrue。"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"], "description": "伝票番号の読み取りの自信度。"},
            "note": {"type": "string", "description": "自信度の理由や、迷った点の短いメモ（日本語）。"},
        },
        "required": ["slip_numbers", "handwritten", "confidence", "note"],
    },
}
