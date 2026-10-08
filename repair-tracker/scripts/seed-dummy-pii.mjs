// 開発用: ダミー案件(has_pii=true)に「架空の」個人情報を暗号化して投入する。
// 本番では実行しない。環境変数: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, PII_KEYS, PII_KEY_CURRENT
import { createClient } from '@supabase/supabase-js'
import { encryptField, keyRingFromEnv } from '../supabase/functions/_shared/crypto.ts'

const need = ['SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'PII_KEYS', 'PII_KEY_CURRENT']
for (const k of need) if (!process.env[k]) { console.error(`環境変数 ${k} が必要です`); process.exit(1) }
if (/supabase\.co/.test(process.env.SUPABASE_URL) && process.env.ALLOW_REMOTE_SEED !== 'yes') {
  console.error('リモート(本番の可能性)のSupabaseへの投入は拒否しました。ローカル環境で実行してください'); process.exit(1)
}
const db = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_ROLE_KEY)
const ring = keyRingFromEnv((k) => process.env[k])
const { data: rows, error } = await db.from('repairs').select('id, mgmt_no').eq('has_pii', true).like('serial_no', 'DUMMY-SN-%')
if (error) throw error
let n = 0
for (const r of rows) {
  n++
  await db.from('repair_pii').upsert({
    repair_id: r.id, key_version: Number(ring.current),
    name_enc: await encryptField(ring, `架空 太郎${n}`, `${r.id}:name`),
    phone_enc: await encryptField(ring, `000-0000-${String(n).padStart(4, '0')}`, `${r.id}:phone`),
    addr_enc: await encryptField(ring, `架空県サンプル市テスト町${n}-1-1`, `${r.id}:addr`),
  })
}
console.log(`${n}件のダミー個人情報を投入しました`)
