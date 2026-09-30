from __future__ import annotations

import argparse
import os
from datetime import datetime

from dotenv import load_dotenv

from . import db
from .collector.csv_collector import CsvCollector
from .config import Config, load_config
from .inventory import store
from .logging_setup import setup_logging
from .notifier.discord import ConsoleNotifier, DiscordNotifier
from .pipeline import run_pipeline


def _build_collector(args, cfg: Config, conn):
    if args.csv:
        return CsvCollector(args.csv), "csv"
    from .collector.playwright_collector import PlaywrightCollector
    from .collector.rate_limiter import RateLimiter

    rl = cfg.raw["rate_limit"]
    limiter = RateLimiter(conn, rl["min_interval_sec"], tuple(rl["jitter_sec"]), rl["max_searches_per_hour"])
    return PlaywrightCollector(cfg.raw["search"]["keywords"], cfg.price_min, cfg.price_max, limiter,
                               headless=not args.headed), "playwright"


def _notifiers(args, cfg: Config):
    url = os.getenv("DISCORD_WEBHOOK_URL", "")
    if not args.dry_run and cfg.raw["notify"]["discord"]["enabled"] and url:
        return [DiscordNotifier(url)]
    return [ConsoleNotifier()]


def _source_args(p: argparse.ArgumentParser) -> None:
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--csv", help="手動CSV取り込み")
    g.add_argument("--playwright", action="store_true", help="Playwrightで公開検索ページを収集")
    p.add_argument("--headed", action="store_true", help="ブラウザを表示して実行")
    p.add_argument("--dry-run", action="store_true", help="通知せず標準出力に表示")


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="sedori")
    ap.add_argument("--config", default="config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="収集→相場算出→利益判定→通知を1回実行")
    _source_args(r)
    r.add_argument("--as-of", help="基準日 YYYY-MM-DD(サンプルCSVの動作確認用)")

    s = sub.add_parser("schedule", help="定期実行(夜間停止は config の schedule.quiet_hours)")
    _source_args(s)

    inv = sub.add_parser("inventory", help="在庫・損益管理").add_subparsers(dest="sub", required=True)
    a = inv.add_parser("add", help="仕入れを登録")
    a.add_argument("title"); a.add_argument("price", type=int)
    a.add_argument("--item-id", default=""); a.add_argument("--date"); a.add_argument("--memo", default="")
    li = inv.add_parser("list", help="在庫一覧")
    li.add_argument("--status", choices=["purchased", "listed", "sold"])
    ls = inv.add_parser("listed", help="出品済みにする")
    ls.add_argument("id", type=int); ls.add_argument("price", type=int); ls.add_argument("--date")
    sd = inv.add_parser("sold", help="売却を記録")
    sd.add_argument("id", type=int); sd.add_argument("price", type=int)
    sd.add_argument("--date"); sd.add_argument("--fee", type=int)
    sd.add_argument("--shipping", type=int, default=0); sd.add_argument("--packing", type=int, default=0)
    inv.add_parser("report", help="月次レポートと滞留在庫")
    ex = inv.add_parser("export", help="確定申告用CSV出力")
    ex.add_argument("path"); ex.add_argument("--year", type=int)

    g = sub.add_parser("listing", help="在庫IDから出品文・推奨価格・値下げ戦略を生成(Claude API)")
    g.add_argument("id", type=int)
    g.add_argument("--condition", required=True, help="状態(事実のみ。傷・付属品など)")
    g.add_argument("--notes", default="", help="追加の事実情報")
    g.add_argument("--shipping", type=int, default=0, help="想定送料(円)")
    return ap


def _cmd_inventory(args, conn, cfg: Config) -> None:
    if args.sub == "add":
        from .pricing.normalizer import normalize_title
        i = store.add_purchase(conn, args.title, args.price, args.item_id, normalize_title(args.title),
                               args.date, args.memo)
        print(f"登録しました: 在庫ID={i}")
    elif args.sub == "list":
        q = "SELECT * FROM inventory" + (" WHERE status=?" if args.status else "") + " ORDER BY id"
        for r in conn.execute(q, (args.status,) if args.status else ()):
            print(f"{r['id']:>4} {r['status']:<9} 仕入{r['purchase_price']:>6} 売価{r['sold_price'] or r['listed_price'] or '-':>6} {r['title']}")
    elif args.sub == "listed":
        store.mark_listed(conn, args.id, args.price, args.date); print("更新しました")
    elif args.sub == "sold":
        store.mark_sold(conn, args.id, args.price, args.date, args.fee, args.shipping, args.packing,
                        cfg.profit.fee_rate)
        print("更新しました")
    elif args.sub == "report":
        print("月       件数     売上     利益  平均回転日数")
        for m in store.monthly_report(conn):
            print(f"{m['month']}  {m['count']:>4} {m['revenue']:>8} {m['profit']:>8}  {m['avg_turnover_days']}")
        st = store.stagnant_stock(conn)
        print(f"\n滞留在庫(30日以上): {len(st)}件")
        for s in st:
            print(f"  ID{s['id']} {s['title']} ({s['age_days']}日, 仕入{s['purchase_price']}円)")
    elif args.sub == "export":
        print(f"{store.export_csv(conn, args.path, args.year)}件を出力: {args.path}")


def _cmd_listing(args, conn, cfg: Config) -> None:
    import anthropic  # ANTHROPIC_API_KEY は環境変数(.env)から読まれる

    from .listing.generator import generate_listing
    from .pricing.market import market_for_key
    from .profit.calculator import shipping_cost

    row = conn.execute("SELECT * FROM inventory WHERE id=?", (args.id,)).fetchone()
    if row is None:
        raise SystemExit(f"在庫ID {args.id} が見つかりません")
    m = market_for_key(conn, row["product_key"], cfg.market)
    facts = {"仕入れ時タイトル": row["title"], "状態": args.condition, "補足": args.notes}
    ship = args.shipping or shipping_cost(row["title"], cfg.profit)
    d = generate_listing(anthropic.Anthropic(), cfg.raw["listing"]["model"], facts,
                         m.median if m else None, row["purchase_price"],
                         cfg.raw["listing"]["markdown_strategy"], cfg.profit.fee_rate, ship,
                         cfg.profit.packing_cost, cfg.profit.min_net_profit)
    print(f"タイトル: {d.title}\n\n{d.description}\n\n推奨価格: {d.recommended_price}円"
          + (f"(相場{m.median}円/{m.count}件{'' if m.reliable else '・信頼度低'})" if m else "(相場なし)"))
    print("値下げ戦略:")
    for p in d.markdown_plan:
        print(f"  {p['after_days']}日後: {p['price']}円")
    for w in d.warnings:
        print(f"[警告] {w}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    load_dotenv()
    cfg = load_config(args.config)
    setup_logging(cfg.log_dir)
    conn = db.connect(cfg.db_path)

    if args.cmd == "run":
        collector, source = _build_collector(args, cfg, conn)
        now = datetime.fromisoformat(args.as_of) if args.as_of else None
        print(run_pipeline(conn, collector, _notifiers(args, cfg), cfg, now=now, source=source))
    elif args.cmd == "schedule":
        from .scheduler import run_forever

        def job() -> None:
            collector, source = _build_collector(args, cfg, conn)
            run_pipeline(conn, collector, _notifiers(args, cfg), cfg, source=source)

        sch = cfg.raw["schedule"]
        run_forever(job, sch["interval_minutes"], sch["quiet_hours"])
    elif args.cmd == "inventory":
        _cmd_inventory(args, conn, cfg)
    elif args.cmd == "listing":
        _cmd_listing(args, conn, cfg)
    return 0
