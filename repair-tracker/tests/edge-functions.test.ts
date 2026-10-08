// @vitest-environment node
// Edge Function の権限判定・暗号化・監査の順序を、Deno/Supabase の偽物で実行して検証する
import { beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { createClient as _c, db, deletedUsers, failures, invited } from './fakes/supabase'

void _c
type H = (r: Request) => Promise<Response>
const handlers: Record<string, H> = {}
const K = Buffer.alloc(32, 7).toString('base64')
const env: Record<string, string> = {
  SUPABASE_URL: 'http://x', SUPABASE_ANON_KEY: 'anon', SUPABASE_SERVICE_ROLE_KEY: 'service',
  PII_KEYS: JSON.stringify({ 1: K }), PII_KEY_CURRENT: '1', ALLOWED_ORIGIN: 'https://app.example.test', SITE_URL: 'https://app.example.test',
}
let current = ''
;(globalThis as unknown as { Deno: unknown }).Deno = { serve: (h: H) => { handlers[current] = h }, env: { get: (k: string) => env[k] } }

const U = { admin: '00000000-0000-4000-8000-0000000000a1', hq: '00000000-0000-4000-8000-0000000000b1', spr: '00000000-0000-4000-8000-0000000000c1',
  fuk: '00000000-0000-4000-8000-0000000000c2', view: '00000000-0000-4000-8000-0000000000d1', off: '00000000-0000-4000-8000-0000000000e1' }
const R1 = '10000000-0000-4000-8000-000000000001' // 札幌(branch 1)
const R2 = '10000000-0000-4000-8000-000000000002' // 福岡(branch 2)
const tok = (sub: string, aal = 'aal2') => `${Buffer.from('{}').toString('base64url')}.${Buffer.from(JSON.stringify({ sub, aal })).toString('base64url')}.s`
const call = (name: string, body: unknown, who?: string, aal?: string) => handlers[name](new Request('http://f/' + name, {
  method: 'POST', headers: { 'content-type': 'application/json', origin: 'https://app.example.test', ...(who ? { authorization: `Bearer ${tok(who, aal)}` } : {}) }, body: JSON.stringify(body) }))

beforeAll(async () => {
  for (const n of ['pii-write', 'pii-reveal', 'csv-export', 'admin-users']) { current = n; await import(process.env.BUNDLED ? `../supabase/functions-bundled/${n}.ts` : `../supabase/functions/${n}/index.ts`) }
})
beforeEach(() => {
  failures.audit = false; invited.length = 0; deletedUsers.length = 0
  for (const k of Object.keys(db)) delete db[k]
  db.profiles = [
    { user_id: U.admin, role: 'admin', branch_id: null, active: true }, { user_id: U.hq, role: 'hq_viewer', branch_id: null, active: true },
    { user_id: U.spr, role: 'branch_staff', branch_id: 1, active: true }, { user_id: U.fuk, role: 'branch_staff', branch_id: 2, active: true },
    { user_id: U.view, role: 'branch_viewer', branch_id: 1, active: true }, { user_id: U.off, role: 'branch_staff', branch_id: 1, active: false },
  ]
  db.repairs = [
    { id: R1, mgmt_no: 'SPR-1', branch_id: 1, deleted_at: null, status: 'received', dealer_name: '=cmd|calc', has_pii: false },
    { id: R2, mgmt_no: 'FUK-1', branch_id: 2, deleted_at: null, status: 'received', dealer_name: '福岡店', has_pii: false },
  ]
  db.repair_pii = []; db.audit_log = []
})

const write = (who: string, id = R1, extra: object = {}) => call('pii-write', { repair_id: id, name: '山田 太郎', phone: '090-1234-5678', address: '架空県サンプル市1-1', ...extra }, who)

describe('共通: 認証・MFA', () => {
  it('未認証は401 / aal1(MFA未通過)は403 / 無効ユーザーは403', async () => {
    expect((await call('pii-reveal', { repair_id: R1 })).status).toBe(401)
    expect((await call('pii-reveal', { repair_id: R1 }, U.spr, 'aal1')).status).toBe(403)
    expect((await call('pii-reveal', { repair_id: R1 }, U.off)).status).toBe(403)
  })
  it('CORSは許可オリジンのみ', async () => {
    const ok = await call('pii-reveal', { repair_id: R1 })
    expect(ok.headers.get('access-control-allow-origin')).toBe('https://app.example.test')
    const evil = await handlers['pii-reveal'](new Request('http://f', { method: 'POST', headers: { origin: 'https://evil.test' }, body: '{}' }))
    expect(evil.headers.get('access-control-allow-origin')).toBe('null')
    expect(evil.headers.get('cache-control')).toBe('no-store')
  })
})

describe('pii-write: 暗号化して保存', () => {
  it('自拠点のstaffは保存でき、DBには暗号文とマスク値のみが残る', async () => {
    expect((await write(U.spr)).status).toBe(200)
    const pii = db.repair_pii[0]
    expect(JSON.stringify(db)).not.toContain('山田 太郎')
    expect(JSON.stringify(db)).not.toContain('090-1234-5678')
    expect(JSON.stringify(db)).not.toContain('サンプル市')
    expect(pii.name_enc).toMatch(/^v1:/)
    const r = db.repairs[0]
    expect(r.enduser_name_mask).toBe('山田 ○○'); expect(r.enduser_phone_mask).toBe('090-****-5678'); expect(r.has_pii).toBe(true)
    expect(db.audit_log[0]).toMatchObject({ action: 'pii_write', actor: U.spr })
    expect(JSON.stringify(db.audit_log)).not.toContain('山田') // 監査ログに値を残さない
  })
  it('他拠点・viewer・hq・不正IDは拒否', async () => {
    expect((await write(U.fuk, R1)).status).toBe(403)
    expect((await write(U.view)).status).toBe(403)
    expect((await write(U.hq)).status).toBe(403)
    expect((await call('pii-write', { repair_id: "1' or '1'='1", name: 'x' }, U.spr)).status).toBe(400)
    expect(db.repair_pii).toHaveLength(0)
  })
  it('入力検証: 長すぎる氏名・不正な電話番号', async () => {
    expect((await write(U.spr, R1, { name: 'あ'.repeat(61) })).status).toBe(400)
    expect((await write(U.spr, R1, { phone: '<script>' })).status).toBe(400)
  })
  it('空文字で項目を削除し、全て空ならhas_piiがfalseになる', async () => {
    await write(U.spr)
    await call('pii-write', { repair_id: R1, name: '', phone: '', address: '' }, U.spr)
    expect(db.repairs[0].has_pii).toBe(false); expect(db.repairs[0].enduser_name_mask).toBeNull()
  })
  it('削除済み案件には書けない', async () => {
    db.repairs[0].deleted_at = '2026-01-01'
    expect((await write(U.spr)).status).toBe(403)
  })
})

describe('pii-reveal: 表示と監査', () => {
  beforeEach(async () => { await write(U.spr); await write(U.fuk, R2); db.audit_log = [] })
  it('自拠点のstaffと管理者は平文を取得でき、監査ログに記録される', async () => {
    const res = await call('pii-reveal', { repair_id: R1 }, U.spr)
    expect(res.status).toBe(200)
    expect(await res.json()).toEqual({ name: '山田 太郎', phone: '090-1234-5678', address: '架空県サンプル市1-1' })
    expect(db.audit_log).toEqual([expect.objectContaining({ action: 'pii_reveal', actor: U.spr, repair_id: R1 })])
    expect((await call('pii-reveal', { repair_id: R2 }, U.admin)).status).toBe(200)
  })
  it('hq_viewer・branch_viewer・他拠点staffは拒否され、監査ログにも「表示」は残らない', async () => {
    for (const who of [U.hq, U.view, U.fuk]) expect((await call('pii-reveal', { repair_id: R1 }, who)).status).toBe(403)
    expect(db.audit_log).toHaveLength(0)
  })
  it('監査ログに記録できない場合は平文を返さない(記録なき閲覧を許さない)', async () => {
    failures.audit = true
    const res = await call('pii-reveal', { repair_id: R1 }, U.spr)
    expect(res.status).toBe(500)
    expect(await res.text()).not.toContain('山田')
  })
  it('10分に30回を超える表示は429', async () => {
    for (let i = 0; i < 30; i++) db.audit_log.push({ actor: U.spr, action: 'pii_reveal', at: new Date().toISOString() })
    const res = await call('pii-reveal', { repair_id: R1 }, U.spr)
    expect(res.status).toBe(429)
    expect(db.audit_log.filter((a) => a.action === 'pii_reveal')).toHaveLength(30) // 拒否時は記録を増やさない
  })
  it('別案件へ暗号文をコピーしても復号できない(AAD束縛)', async () => {
    db.repair_pii.find((p) => p.repair_id === R2)!.name_enc = db.repair_pii.find((p) => p.repair_id === R1)!.name_enc
    const res = await call('pii-reveal', { repair_id: R2 }, U.fuk)
    expect(res.status).toBe(500)
    expect(await res.text()).not.toContain('山田')
  })
  it('匿名化済み(暗号文なし)でも落ちずにnullを返す', async () => {
    db.repair_pii = []
    expect(await (await call('pii-reveal', { repair_id: R1 }, U.spr)).json()).toEqual({ name: null, phone: null, address: null })
  })
})

describe('csv-export', () => {
  const csv = async (who: string, body: object = {}) => call('csv-export', body, who)
  it('viewerは出力不可、個人情報列はadmin以外は不可', async () => {
    expect((await csv(U.view)).status).toBe(403)
    expect((await csv(U.hq, { include_pii: true })).status).toBe(403)
    expect((await csv(U.spr, { include_pii: true })).status).toBe(403)
  })
  it('既定は個人情報列なし。RLS相当で自拠点のみ。数式インジェクションは無害化。出力が監査される', async () => {
    await write(U.spr); db.audit_log = []
    const res = await csv(U.spr)
    const bytes = new Uint8Array(await res.clone().arrayBuffer())
    const text = await res.text()
    expect(res.status).toBe(200); expect([...bytes.slice(0, 3)]).toEqual([0xef, 0xbb, 0xbf]) // UTF-8 BOM(Excelの文字化け対策)
    expect(text).toContain('SPR-1'); expect(text).not.toContain('FUK-1')
    expect(text).not.toContain('山田'); expect(text).not.toContain('enduser_name,')
    expect(text).toContain("'=cmd|calc")
    expect(db.audit_log[0]).toMatchObject({ action: 'export', meta: expect.objectContaining({ row_count: 1, include_pii: false }) })
  })
  it('hqは全拠点(個人情報列なし)', async () => {
    const t = await (await csv(U.hq)).text()
    expect(t).toContain('SPR-1'); expect(t).toContain('FUK-1')
  })
  it('adminが明示した場合のみ個人情報を含み、その旨が監査される', async () => {
    await write(U.spr); db.audit_log = []
    const t = await (await csv(U.admin, { include_pii: true })).text()
    expect(t).toContain('enduser_name'); expect(t).toContain('山田 太郎')
    expect(db.audit_log[0].meta.include_pii).toBe(true)
  })
})

describe('admin-users', () => {
  const inv = { action: 'invite', email: 'new@example.co.jp', display_name: '新人', role: 'branch_staff', branch_id: 1 }
  it('admin以外は拒否', async () => {
    for (const who of [U.hq, U.spr, U.view]) expect((await call('admin-users', inv, who)).status).toBe(403)
    expect(invited).toHaveLength(0)
  })
  it('adminは招待でき、プロファイル作成と監査記録が行われる', async () => {
    expect((await call('admin-users', inv, U.admin)).status).toBe(200)
    expect(invited).toEqual(['new@example.co.jp'])
    expect(db.profiles.find((p) => p.display_name === '新人')).toMatchObject({ role: 'branch_staff', branch_id: 1 })
    expect(db.audit_log[0].action).toBe('user_invite')
  })
  it('不正な入力(メール・権限・拠点なし)は拒否', async () => {
    expect((await call('admin-users', { ...inv, email: 'bad' }, U.admin)).status).toBe(400)
    expect((await call('admin-users', { ...inv, role: 'root' }, U.admin)).status).toBe(400)
    expect((await call('admin-users', { ...inv, branch_id: null }, U.admin)).status).toBe(400)
    expect(invited).toHaveLength(0)
  })
  it('MFA再設定は監査される。不正IDは拒否', async () => {
    expect((await call('admin-users', { action: 'reset_mfa', user_id: U.spr }, U.admin)).status).toBe(200)
    expect(db.audit_log[0].action).toBe('mfa_reset')
    expect((await call('admin-users', { action: 'reset_mfa', user_id: 'x' }, U.admin)).status).toBe(400)
  })
})
