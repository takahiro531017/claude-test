import type { Page, Route } from '@playwright/test'

export const API = 'http://127.0.0.1:54321'
const b64 = (o: unknown) => Buffer.from(JSON.stringify(o)).toString('base64url')
const jwt = (sub: string, aal: 'aal1' | 'aal2') =>
  `${b64({ alg: 'HS256', typ: 'JWT' })}.${b64({ sub, aal, role: 'authenticated', exp: 4102444800, amr: [{ method: 'password', timestamp: 1 }] })}.sig`

export type Role = 'admin' | 'hq_viewer' | 'branch_staff' | 'branch_viewer'
export function makeRepair(over: Record<string, unknown> = {}) {
  return {
    id: '20000000-0000-0000-0000-000000000001', mgmt_no: 'SPR-20261008-001', branch_id: 1, received_on: '2026-10-08', status: 'received',
    priority: 'normal', due_on: null, dealer_id: 1, dealer_name: 'テスト家電センター', dealer_code: 'D002', dealer_contact_name: null, dealer_contact: null,
    manufacturer_id: 1, product_name: 'ドラム式洗濯機', model_no: 'MODEL-001', serial_no: 'DUMMY-SN-00001', purchased_on: null, has_warranty_card: false,
    in_warranty: null, accessories: [], symptom: '電源が入らない', appearance_note: null, enduser_name_mask: '架空 ○○', enduser_phone_mask: '000-****-0001',
    has_pii: true, maker_receipt_no: null, maker_sent_on: null, outbound_carrier: null, outbound_tracking_no: null, quote_amount: null, quote_approved: null,
    repair_detail: null, repair_cost: null, maker_returned_on: null, dealer_returned_on: null, return_carrier: null, return_tracking_no: null,
    completed_on: null, note: null, version: 1, created_by: 'u1', created_at: '2026-10-08T01:00:00Z', updated_by: 'u1', updated_at: '2026-10-08T01:00:00Z',
    deleted_at: null, pii_purged_at: null, ...over,
  }
}

export type Mock = { calls: { method: string; url: string; body: string }[]; repairs: ReturnType<typeof makeRepair>[]; conflictOnRpc: boolean }

/** Supabase(Auth / PostgREST / Functions)の最小モック */
export async function mockBackend(page: Page, role: Role = 'branch_staff'): Promise<Mock> {
  const uid = 'u1'
  let aal: 'aal1' | 'aal2' = 'aal1' // MFA確認後は以降のトークン更新でも維持される(実サーバーと同じ)
  const mock: Mock = { calls: [], repairs: [makeRepair()], conflictOnRpc: false }
  const user = { id: uid, email: 'staff@example.test', aud: 'authenticated', role: 'authenticated', app_metadata: {}, user_metadata: {}, created_at: '2026-01-01T00:00:00Z',
    factors: [{ id: 'f1', factor_type: 'totp', status: 'verified', friendly_name: 'app', created_at: '2026-01-01', updated_at: '2026-01-01' }] }
  const session = (aal: 'aal1' | 'aal2') => ({ access_token: jwt(uid, aal), token_type: 'bearer', expires_in: 3600, expires_at: 4102444800, refresh_token: 'r', user })
  const profile = { user_id: uid, display_name: 'テスト太郎', role, branch_id: role === 'admin' || role === 'hq_viewer' ? null : 1, active: true, created_at: '2026-01-01T00:00:00Z' }

  await page.route(`${API}/**`, async (route: Route) => {
    const req = route.request(); const url = new URL(req.url()); const p = url.pathname
    const cors = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': '*' }
    const send = (status: number, body: unknown, extra: Record<string, string> = {}) =>
      route.fulfill({ status, headers: { ...cors, 'content-type': 'application/json', ...extra }, body: body === undefined ? '' : JSON.stringify(body) })
    if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: cors })
    mock.calls.push({ method: req.method(), url: req.url(), body: req.postData() ?? '' })
    const single = (req.headers()['accept'] ?? '').includes('vnd.pgrst.object')
    const rows = (all: unknown[]) => (single ? send(200, all[0] ?? null) : send(200, all))

    if (p === '/auth/v1/token') return send(200, session(url.searchParams.get('grant_type') === 'password' ? 'aal1' : aal))
    if (p === '/auth/v1/user') return send(200, user)
    if (/\/factors\/f1\/challenge$/.test(p)) return send(200, { id: 'c1', type: 'totp', expires_at: 4102444800 })
    if (/\/factors\/f1\/verify$/.test(p)) { aal = 'aal2'; return send(200, session('aal2')) }
    if (p === '/auth/v1/logout') return route.fulfill({ status: 204, headers: cors })
    if (p === '/rest/v1/profiles') return rows(url.searchParams.has('user_id') ? [profile] : [profile])
    if (p === '/rest/v1/branches') return send(200, [{ id: 1, code: 'SPR', name: '札幌支店', active: true }, { id: 2, code: 'FUK', name: '福岡支店', active: true }])
    if (p === '/rest/v1/manufacturers') return send(200, [{ id: 1, name: 'パナソニック', active: true }])
    if (p === '/rest/v1/dealers') return send(200, [{ id: 1, code: 'D002', name: 'テスト家電センター', active: true }])
    if (p === '/rest/v1/settings') return send(200, [{ key: 'stale_sent_days', value: '14' }, { key: 'stale_return_days', value: '7' }, { key: 'retention_years', value: '3' }, { key: 'session_timeout_min', value: '30' }])
    if (p === '/rest/v1/status_history') return send(200, [{ id: 1, from_status: null, to_status: 'received', changed_by: uid, changed_at: '2026-10-08T01:00:00Z', comment: null }])
    if (p === '/rest/v1/repair_files') return send(200, [])
    if (p === '/rest/v1/rpc/log_event') return route.fulfill({ status: 204, headers: cors })
    if (p === '/rest/v1/rpc/serial_exists_elsewhere') return send(200, false)
    if (p === '/rest/v1/rpc/change_status') {
      if (mock.conflictOnRpc) return send(400, { code: '40001', message: 'conflict' })
      const b = JSON.parse(req.postData() ?? '{}'); const r = mock.repairs[0]
      Object.assign(r, { status: b.p_to, version: r.version + 1 }); return send(200, r)
    }
    if (p === '/rest/v1/repairs') return req.method() === 'GET' ? (single ? send(200, mock.repairs.find((r) => url.searchParams.get('id')?.endsWith(r.id)) ?? null) : send(200, mock.repairs)) : send(200, mock.repairs[0])
    if (p === '/functions/v1/pii-reveal') return send(200, { name: '架空 太郎', phone: '000-0000-0001', address: '架空県サンプル市テスト町1-1-1' })
    return send(404, { message: `unmocked ${p}` })
  })
  await page.route('**/realtime/**', (r) => r.abort())
  return mock
}

export async function login(page: Page) {
  await page.goto('/')
  await page.getByLabel('メールアドレス').fill('staff@example.test')
  await page.getByLabel('パスワード').fill('dummy-password-123')
  await page.getByRole('button', { name: 'ログイン' }).click()
  await page.getByLabel('認証アプリの6桁のコード').fill('123456')
  await page.getByRole('button', { name: '確認' }).click()
  await page.getByRole('heading', { name: /ダッシュボード/ }).waitFor() // セッション保存完了まで待つ
}
