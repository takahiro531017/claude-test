import { describe, expect, it } from 'vitest'
import { decryptField, encryptField, keyRingFromEnv, keyVersionOf, reencryptField } from '../supabase/functions/_shared/crypto'
import { maskName, maskPhone } from '../supabase/functions/_shared/mask'
import { csvCell, isEmail, isUuid } from '../supabase/functions/_shared/validate'

const k1 = btoa(String.fromCharCode(...new Uint8Array(32).fill(1)))
const k2 = btoa(String.fromCharCode(...new Uint8Array(32).fill(2)))
const env = (m: Record<string, string>) => (k: string) => m[k]

describe('暗号化 (AES-256-GCM)', () => {
  const ring = keyRingFromEnv(env({ PII_KEYS: JSON.stringify({ 1: k1 }), PII_KEY_CURRENT: '1' }))
  it('往復でき、平文が暗号文に含まれない', async () => {
    const c = await encryptField(ring, '山田 太郎', 'r1:name')
    expect(c).not.toContain('山田')
    expect(c.startsWith('v1:')).toBe(true)
    expect(await decryptField(ring, c, 'r1:name')).toBe('山田 太郎')
  })
  it('同じ平文でも毎回異なる暗号文(IVがランダム)', async () => {
    expect(await encryptField(ring, 'x', 'a')).not.toBe(await encryptField(ring, 'x', 'a'))
  })
  it('別案件/別項目への移し替え(AAD不一致)は復号失敗', async () => {
    const c = await encryptField(ring, '090-1234-5678', 'r1:phone')
    await expect(decryptField(ring, c, 'r2:phone')).rejects.toThrow()
  })
  it('改ざんされた暗号文は復号失敗', async () => {
    const c = await encryptField(ring, 'abc', 'a')
    const t = c.slice(0, -4) + (c.slice(-4) === 'AAAA' ? 'BBBB' : 'AAAA')
    await expect(decryptField(ring, t, 'a')).rejects.toThrow()
  })
  it('鍵ローテーション: 旧鍵の暗号文も新リングで復号できる', async () => {
    const old = await encryptField(ring, '旧データ', 'a')
    const ring2 = keyRingFromEnv(env({ PII_KEYS: JSON.stringify({ 1: k1, 2: k2 }), PII_KEY_CURRENT: '2' }))
    expect(await decryptField(ring2, old, 'a')).toBe('旧データ')
    expect(keyVersionOf(await encryptField(ring2, 'n', 'a'))).toBe(2)
  })
  it('再暗号化: 新鍵に切り替わり、平文は変わらず、AADも維持される', async () => {
    const r1 = keyRingFromEnv(env({ PII_KEYS: JSON.stringify({ 1: k1 }), PII_KEY_CURRENT: '1' }))
    const r2 = keyRingFromEnv(env({ PII_KEYS: JSON.stringify({ 1: k1, 2: k2 }), PII_KEY_CURRENT: '2' }))
    const old = await encryptField(r1, '住所テスト', 'r9:addr')
    const neu = await reencryptField(r2, old, 'r9:addr')
    expect(keyVersionOf(neu)).toBe(2)
    expect(await decryptField(r2, neu, 'r9:addr')).toBe('住所テスト')
    await expect(decryptField(r2, neu, 'r8:addr')).rejects.toThrow()
    // 旧鍵を取り除いたリングでも新暗号文は復号できる(=旧鍵の廃棄が可能)
    const r2only = keyRingFromEnv(env({ PII_KEYS: JSON.stringify({ 2: k2 }), PII_KEY_CURRENT: '2' }))
    expect(await decryptField(r2only, neu, 'r9:addr')).toBe('住所テスト')
  })
  it('鍵未設定・不正長の鍵はエラー', async () => {
    expect(() => keyRingFromEnv(env({}))).toThrow()
    const bad = keyRingFromEnv(env({ PII_KEYS: JSON.stringify({ 1: btoa('short') }), PII_KEY_CURRENT: '1' }))
    await expect(encryptField(bad, 'x', 'a')).rejects.toThrow()
  })
})

describe('マスク', () => {
  it('氏名', () => {
    expect(maskName('山田 太郎')).toBe('山田 ○○')
    expect(maskName('山田　太郎')).toBe('山田 ○○')
    expect(maskName('山田太郎')).toBe('山○○○')
    expect(maskName('')).toBe('')
  })
  it('電話番号', () => {
    expect(maskPhone('090-1234-5678')).toBe('090-****-5678')
    expect(maskPhone('0312345678')).toBe('031-****-5678')
    expect(maskPhone('123')).toBe('***')
  })
})

describe('検証・CSV', () => {
  it('CSV数式インジェクションを無害化', () => {
    expect(csvCell('=HYPERLINK("x")')).toBe(`"'=HYPERLINK(""x"")"`)
    expect(csvCell('+1')).toBe("'+1")
    expect(csvCell('a,b')).toBe('"a,b"')
    expect(csvCell(null)).toBe('')
  })
  it('UUID/メール', () => {
    expect(isUuid('00000000-0000-0000-0000-0000000000a1')).toBe(true)
    expect(isUuid("1' or '1'='1")).toBe(false)
    expect(isEmail('a@example.co.jp')).toBe(true)
    expect(isEmail('a b@x')).toBe(false)
  })
})
