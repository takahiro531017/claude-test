import { expect, test } from '@playwright/test'
import { login, mockBackend } from './mock-backend'

test('ログイン→MFA→ダッシュボード。操作はログに記録される', async ({ page }) => {
  const mock = await mockBackend(page)
  await login(page)
  await expect(page.getByRole('heading', { name: /ダッシュボード/ })).toBeVisible()
  await expect(page.getByText('札幌担当').or(page.getByText('テスト太郎'))).toBeVisible()
  expect(mock.calls.some((c) => c.url.includes('/rpc/log_event') && c.body.includes('login'))).toBe(true)
})

test('MFA未通過ではアプリ画面に入れない', async ({ page }) => {
  await mockBackend(page)
  await page.goto('/')
  await page.getByLabel('メールアドレス').fill('staff@example.test')
  await page.getByLabel('パスワード').fill('dummy-password-123')
  await page.getByRole('button', { name: 'ログイン' }).click()
  await expect(page.getByRole('heading', { name: '認証コードの入力' })).toBeVisible()
  await expect(page.getByRole('link', { name: '修理品一覧' })).toHaveCount(0)
})

test('一覧は個人情報をマスク表示し、検索語は無害化されて送信される', async ({ page }) => {
  const mock = await mockBackend(page)
  await login(page)
  await page.getByRole('link', { name: '修理品一覧' }).click()
  await expect(page.getByText('SPR-20261008-001')).toBeVisible()
  await expect(page.getByText('架空 ○○')).toBeVisible()
  await expect(page.getByText('架空 太郎')).toHaveCount(0)
  await page.getByLabel('検索').fill('SPR-1,id.eq.1)or(x')
  await expect.poll(() => mock.calls.some((c) => c.url.includes('ilike'))).toBe(true)
  // 検索語に , ( ) を混ぜても or 条件の数が増えない(=フィルタ構文を注入できない)ことを確認
  const u = new URL(mock.calls.filter((c) => c.url.includes('ilike')).at(-1)!.url)
  const or = u.searchParams.get('or')!
  expect(or.startsWith('(') && or.endsWith(')')).toBe(true)
  const conds = or.slice(1, -1).split(',')
  expect(conds).toHaveLength(7)
  for (const c of conds) expect(c).toMatch(/^[a-z_]+\.ilike\.%[^,()]*%$/)
})

test('詳細: 次へ進めるボタンでステータスが変わり、競合時は警告が出る', async ({ page }) => {
  const mock = await mockBackend(page)
  await login(page)
  await page.goto('/repairs/20000000-0000-0000-0000-000000000001')
  await expect(page.getByRole('heading', { name: /SPR-20261008-001/ })).toBeVisible()
  await page.getByRole('button', { name: /次へ進める → メーカー発送済/ }).click()
  await expect.poll(() => mock.calls.some((c) => c.url.includes('/rpc/change_status') && c.body.includes('sent_to_maker'))).toBe(true)
  mock.conflictOnRpc = true
  await page.getByRole('button', { name: /次へ進める/ }).click()
  await expect(page.getByText('他のユーザーが先に更新しました', { exact: false }).first()).toBeVisible()
})

test('個人情報の表示ボタン: 押した時だけ平文。storage/コンソールに平文を残さない', async ({ page }) => {
  await mockBackend(page)
  const logs: string[] = []
  page.on('console', (m) => logs.push(m.text()))
  await login(page)
  await page.goto('/repairs/20000000-0000-0000-0000-000000000001')
  await expect(page.getByText('架空 ○○')).toBeVisible()
  await expect(page.getByText('架空 太郎')).toHaveCount(0)
  await page.getByRole('button', { name: /表示する/ }).click()
  await expect(page.getByText('架空 太郎')).toBeVisible()
  await expect(page.getByText('あと', { exact: false })).toBeVisible()
  const stored = await page.evaluate(() => JSON.stringify({ l: { ...localStorage }, s: { ...sessionStorage } }))
  expect(stored).not.toContain('架空 太郎')
  expect(stored).not.toContain('000-0000-0001')
  expect(logs.join('\n')).not.toContain('架空 太郎')
  expect(page.url()).not.toContain('架空')
})

test('閲覧専用ユーザーには新規受付・個人情報表示・編集の導線がない', async ({ page }) => {
  await mockBackend(page, 'branch_viewer')
  await login(page)
  await expect(page.getByRole('link', { name: '新規受付' })).toHaveCount(0)
  await page.goto('/repairs/20000000-0000-0000-0000-000000000001')
  await expect(page.getByRole('heading', { name: /SPR-20261008-001/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /表示する/ })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /次へ進める/ })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '変更を保存' })).toHaveCount(0)
})

test('管理画面は管理者のみ', async ({ page }) => {
  await mockBackend(page, 'branch_staff')
  await login(page)
  await expect(page.getByRole('link', { name: '管理' })).toHaveCount(0)
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'ダッシュボード' })).toBeVisible()
})

test('福岡のみ(拠点が1つ)の運用: 拠点別件数・拠点フィルタ・拠点選択を表示しない', async ({ page }) => {
  await mockBackend(page, 'admin', { singleBranch: true })
  await login(page)
  await expect(page.getByRole('heading', { name: /ダッシュボード/ })).toBeVisible()
  await expect(page.getByRole('heading', { name: '拠点別件数' })).toHaveCount(0)
  await page.getByRole('link', { name: '修理品一覧' }).click()
  await expect(page.getByLabel('拠点', { exact: true })).toHaveCount(0)
  await page.getByRole('link', { name: '新規受付' }).click()
  await expect(page.getByRole('heading', { name: '新規受付' })).toBeVisible()
  await expect(page.getByText('受付拠点')).toHaveCount(0)
})

test('複数拠点のときは拠点別件数を表示する(将来の拡大時)', async ({ page }) => {
  await mockBackend(page, 'admin')
  await login(page)
  await expect(page.getByRole('heading', { name: '拠点別件数' })).toBeVisible()
})
