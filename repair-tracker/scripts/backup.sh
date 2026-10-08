#!/usr/bin/env bash
# DB日次バックアップ(age で暗号化)。DATABASE_URL と BACKUP_AGE_RECIPIENT(公開鍵)を環境変数で渡す。
# 秘密鍵(復元時に必要)は DB・リポジトリとは別の場所に保管すること。
# 使い方: DATABASE_URL=... BACKUP_AGE_RECIPIENT=age1... ./scripts/backup.sh [出力ディレクトリ]
set -euo pipefail
: "${DATABASE_URL:?DATABASE_URL が未設定です}"
: "${BACKUP_AGE_RECIPIENT:?BACKUP_AGE_RECIPIENT(age公開鍵)が未設定です}"
OUT="${1:-backups}"; KEEP_DAYS="${KEEP_DAYS:-30}"
mkdir -p "$OUT"; umask 077
FILE="$OUT/repair-$(date +%Y%m%d-%H%M%S).dump.age"
# 平文のダンプをディスクに残さないようパイプで暗号化する
pg_dump --format=custom --no-owner --no-privileges --schema=public --schema=auth "$DATABASE_URL" \
  | age -r "$BACKUP_AGE_RECIPIENT" > "$FILE"
[ -s "$FILE" ] || { echo "バックアップが空です"; rm -f "$FILE"; exit 1; }
find "$OUT" -name 'repair-*.dump.age' -mtime +"$KEEP_DAYS" -delete
echo "OK: $FILE ($(du -h "$FILE" | cut -f1))"
