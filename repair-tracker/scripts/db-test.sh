#!/usr/bin/env bash
# ローカルPostgreSQLでマイグレーション+RLSテストを実行する。
# 使い方: PGHOST=... PGPORT=... PGUSER=postgres ./scripts/db-test.sh
set -euo pipefail
cd "$(dirname "$0")/.."
DB=repair_test
psql -v ON_ERROR_STOP=1 -q -d postgres -c "drop database if exists $DB" -c "create database $DB"
run() { psql -v ON_ERROR_STOP=1 -q -d "$DB" -f "$1"; }
run supabase/tests/00_stub_supabase.sql
for f in supabase/migrations/*.sql; do echo "migrate: $f"; run "$f"; done
run supabase/seed/seed_master.sql
run supabase/seed/seed_branches_all.sql   # 拠点間の分離を検証するため複数拠点が必要
run supabase/tests/10_rls_test.sql
echo "ALL DB TESTS PASSED"
