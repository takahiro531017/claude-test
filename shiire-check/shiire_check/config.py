"""設定ファイル(config.yaml)の読み込み・ログ設定。"""
from __future__ import annotations

import copy
import logging
import logging.handlers
import os
import sys
from pathlib import Path

import yaml

DEFAULTS: dict = {
    "model": "claude-sonnet-5-5",
    "max_tokens": 1024,
    "api_timeout_sec": 60,
    "api_max_retries": 2,
    "workers": 4,
    "api_key": "",
    "api_key_file": "",
    "image": {"max_long_edge": 1568, "jpeg_quality": 85, "pdf_dpi": 200, "max_pdf_pages": 200},
    "scan": {"recursive": False},
    "normalize": {
        "nfkc": True,
        "uppercase": True,
        "remove_whitespace": True,
        "remove_chars": ["-", "‐", "‑", "‒", "–", "—", "―", "−", "ー", "_", ".", "/", "#", "・"],
        "strip_leading_zeros": True,
        "strip_prefixes": [],
    },
    "matching": {
        "min_confidence": "medium",
        "review_if_handwritten": True,
        "multi_candidate_policy": "prefer_ledger",
        "amount_tolerance": 0,
        "date_tolerance_days": 0,
    },
    "data_dir": "",
    "mock": {"readings_file": "_mock_readings.json"},
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def find_config_path(explicit: str | None = None) -> Path | None:
    cands = [explicit, os.environ.get("SHIIRE_CONFIG")]
    cands = [Path(c) for c in cands if c]
    cands += [Path.cwd() / "config.yaml", _app_dir() / "config.yaml"]
    for p in cands:
        if p.is_file():
            return p
    return None


def load_config(explicit: str | None = None) -> dict:
    path = find_config_path(explicit)
    user = {}
    if path:
        with open(path, encoding="utf-8") as f:
            user = yaml.safe_load(f) or {}
        if not isinstance(user, dict):
            raise ValueError(f"設定ファイルの形式が正しくありません: {path}")
    cfg = _merge(DEFAULTS, user)
    cfg["_config_path"] = str(path) if path else ""
    return cfg


def data_dir(cfg: dict) -> Path:
    if cfg.get("data_dir"):
        d = Path(cfg["data_dir"])
    else:
        base = os.environ.get("LOCALAPPDATA")
        d = Path(base) / "ShiireCheck" if base else Path.home() / ".local" / "share" / "ShiireCheck"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_api_key(cfg: dict) -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key.strip()
    if cfg.get("api_key_file"):
        try:
            return Path(cfg["api_key_file"]).read_text(encoding="utf-8").strip() or None
        except OSError:
            return None
    return (cfg.get("api_key") or "").strip() or None


def setup_logging(cfg: dict) -> Path:
    """ログはローカルのみ。伝票番号・金額などの内容は書かず、ファイル名と件数程度にとどめる。"""
    log_path = data_dir(cfg) / "shiire_check.log"
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        h = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(h)
    return log_path
