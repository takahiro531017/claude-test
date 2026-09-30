from __future__ import annotations

import argparse
import os
from datetime import datetime

from dotenv import load_dotenv

from . import db
from .collector.csv_collector import CsvCollector
from .config import load_config
from .logging_setup import setup_logging
from .notifier.discord import ConsoleNotifier, DiscordNotifier
from .pipeline import run_pipeline


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sedori")
    ap.add_argument("--config", default="config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="CSVを取り込み、相場算出→利益判定→通知")
    r.add_argument("--csv", required=True)
    r.add_argument("--dry-run", action="store_true", help="通知せず標準出力に表示")
    r.add_argument("--as-of", help="基準日 YYYY-MM-DD(サンプルCSVの動作確認用)")
    args = ap.parse_args(argv)

    load_dotenv()
    cfg = load_config(args.config)
    setup_logging(cfg.log_dir)
    conn = db.connect(cfg.db_path)

    if args.cmd == "run":
        notifiers = [ConsoleNotifier()]
        url = os.getenv("DISCORD_WEBHOOK_URL", "")
        if not args.dry_run and cfg.raw["notify"]["discord"]["enabled"] and url:
            notifiers = [DiscordNotifier(url)]
        stats = run_pipeline(
            conn, CsvCollector(args.csv), notifiers, cfg,
            now=datetime.fromisoformat(args.as_of) if args.as_of else None,
        )
        print(stats)
    return 0
