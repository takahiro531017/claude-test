#!/usr/bin/env bash
# バックアップの復元。既存データを上書きするため、必ず「空の新しいDB」か検証用DBに対して実行すること。
# 使い方: ./scripts/restore.sh <バックアップファイル.dump.age> <age秘密鍵ファイル> <復元先のDATABASE_URL>
set -euo pipefail
[ $# -eq 3 ] || { echo "使い方: $0 <backup.dump.age> <age-secret-key-file> <target DATABASE_URL>"; exit 2; }
BACKUP="$1"; KEY="$2"; TARGET="$3"
read -r -p "復元先 ${TARGET%%@*}@... のデータを上書きします。よろしいですか? (yes/no) " ans
[ "$ans" = "yes" ] || { echo "中止しました"; exit 1; }
age -d -i "$KEY" "$BACKUP" | pg_restore --clean --if-exists --no-owner --no-privileges --exit-on-error -d "$TARGET"
echo "復元完了。続けて scripts/verify-restore.sql の内容(件数確認・監査ログ検証)を実行してください"
