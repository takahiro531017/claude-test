// AES-256-GCM による個人情報の暗号化。Web Crypto のみ使用(Deno / Node どちらでも動作)。
// 鍵は環境変数(Edge Function のシークレット)にのみ置く。DB には置かない。
//   PII_KEYS        : {"1":"<base64 32byte>","2":"<base64 32byte>"}  (ローテーション時は新しい番号を追加)
//   PII_KEY_CURRENT : 暗号化に使う鍵番号(例 "2")
// 保存形式: v<鍵番号>:<iv base64>:<暗号文+認証タグ base64>

export type KeyRing = { keys: Record<string, string>; current: string }

export function keyRingFromEnv(get: (k: string) => string | undefined): KeyRing {
  const raw = get('PII_KEYS')
  const current = get('PII_KEY_CURRENT')
  if (!raw || !current) throw new Error('暗号鍵が設定されていません')
  const keys = JSON.parse(raw) as Record<string, string>
  if (!keys[current]) throw new Error('現在の鍵番号に対応する鍵がありません')
  return { keys, current }
}

const b64 = (u: Uint8Array) => btoa(String.fromCharCode(...u))
const unb64 = (s: string) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0))

async function importKey(b64key: string): Promise<CryptoKey> {
  const raw = unb64(b64key)
  if (raw.length !== 32) throw new Error('鍵は32バイト(AES-256)である必要があります')
  return crypto.subtle.importKey('raw', raw, 'AES-GCM', false, ['encrypt', 'decrypt'])
}

/** 案件IDを AAD に束縛し、暗号文を別案件へ移し替えても復号できないようにする */
export async function encryptField(ring: KeyRing, plain: string, aad: string): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const key = await importKey(ring.keys[ring.current])
  const ct = new Uint8Array(
    await crypto.subtle.encrypt({ name: 'AES-GCM', iv, additionalData: new TextEncoder().encode(aad) }, key, new TextEncoder().encode(plain)),
  )
  return `v${ring.current}:${b64(iv)}:${b64(ct)}`
}

export async function decryptField(ring: KeyRing, stored: string, aad: string): Promise<string> {
  const m = /^v(\d+):([A-Za-z0-9+/=]+):([A-Za-z0-9+/=]+)$/.exec(stored)
  if (!m) throw new Error('暗号文の形式が不正です')
  const k = ring.keys[m[1]]
  if (!k) throw new Error('該当する鍵がありません')
  const key = await importKey(k)
  const pt = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: unb64(m[2]), additionalData: new TextEncoder().encode(aad) }, key, unb64(m[3]))
  return new TextDecoder().decode(pt)
}

export function keyVersionOf(stored: string): number {
  const m = /^v(\d+):/.exec(stored)
  return m ? Number(m[1]) : 0
}
