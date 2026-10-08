// 暗号鍵のローテーション: repair_pii の全暗号文を「現在の鍵(PII_KEY_CURRENT)」で再暗号化する。
// 手順は docs/セキュリティ設計書.md の「鍵のローテーション」を参照。
// 環境変数: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, PII_KEYS(旧鍵+新鍵の両方を含む), PII_KEY_CURRENT(新鍵の番号)
// 使い方: node scripts/rotate-pii-key.mjs          # ドライラン(件数のみ表示)
//         node scripts/rotate-pii-key.mjs --apply  # 実行
import { createClient } from '@supabase/supabase-js'
import { keyRingFromEnv, keyVersionOf, reencryptField } from '../supabase/functions/_shared/crypto.ts'

for (const k of ['SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'PII_KEYS', 'PII_KEY_CURRENT']) {
  if (!process.env[k]) { console.error(`環境変数 ${k} が必要です`); process.exit(1) }
}
const apply = process.argv.includes('--apply')
const db = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_ROLE_KEY)
const ring = keyRingFromEnv((k) => process.env[k])
const cur = Number(ring.current)
const fields = [['name_enc', 'name'], ['phone_enc', 'phone'], ['addr_enc', 'addr']]

let scanned = 0, todo = 0, done = 0
for (let from = 0; ; from += 500) {
  const { data, error } = await db.from('repair_pii').select('*').order('repair_id').range(from, from + 499)
  if (error) { console.error('取得に失敗しました'); process.exit(1) }
  if (!data.length) break
  for (const row of data) {
    scanned++
    const patch = {}
    for (const [col, aad] of fields) {
      if (row[col] && keyVersionOf(row[col]) !== cur) patch[col] = await reencryptField(ring, row[col], `${row.repair_id}:${aad}`)
    }
    if (!Object.keys(patch).length) continue
    todo++
    if (apply) {
      const { error: e } = await db.from('repair_pii').update({ ...patch, key_version: cur, updated_at: new Date().toISOString() }).eq('repair_id', row.repair_id)
      if (e) { console.error('更新に失敗しました。中断します(再実行しても安全です)'); process.exit(1) }
      done++
    }
  }
}
console.log(`確認 ${scanned}件 / 再暗号化が必要 ${todo}件 / 実行 ${done}件${apply ? '' : '  (ドライラン: --apply で実行)'}`)
