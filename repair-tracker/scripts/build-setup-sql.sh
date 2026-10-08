#!/usr/bin/env bash
# Supabase の SQL Editor に「貼り付けて1回実行」するだけで初期構築できる単一ファイルを生成する。
# マイグレーション(1〜4)と福岡支店の初期マスタをまとめる。migrations/ を変更したら再生成すること。
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=supabase/setup_all_in_one.sql
{
  echo "-- ============================================================================"
  echo "-- 修理品管理システム 初期構築SQL(自動生成: scripts/build-setup-sql.sh)"
  echo "-- Supabase ダッシュボード → SQL Editor に全文を貼り付けて Run を1回だけ実行する。"
  echo "-- 内容: スキーマ / トリガー / 権限(RLS) / 監査ログ / 写真バケット / 福岡支店とメーカーの初期マスタ"
  echo "-- ※ 1つのプロジェクトにつき1回だけ実行すること(2回目はエラーになる)。個人情報は含まない。"
  echo "-- ============================================================================"
  for f in supabase/migrations/20261008000001_core_schema.sql supabase/migrations/20261008000002_functions_triggers.sql \
           supabase/migrations/20261008000003_rls.sql supabase/migrations/20261008000004_audit_verify.sql supabase/seed/seed_master.sql; do
    echo; echo "-- ---------- $(basename "$f") ----------"; cat "$f"
  done
} > "$OUT"
echo "生成: $OUT ($(wc -c < "$OUT") bytes)"
