import { supabase } from './supabase'
import { searchFilter } from './search'
import type { Branch, Dealer, FileRow, HistoryRow, Named, Profile, Repair, Settings } from './types'
import { DEFAULT_SETTINGS } from './types'
import { extFor, sniffMime, validateFile } from './files'

export class ConflictError extends Error {
  constructor() { super('他のユーザーが先に更新しました') }
}
const fail = (msg: string) => new Error(msg) // 内部エラー詳細(個人情報を含み得る)は画面に出さない

export type ListFilters = {
  q?: string; branchId?: number; status?: string; manufacturerId?: number; from?: string; to?: string
  sort?: 'updated_at' | 'received_on' | 'mgmt_no'; asc?: boolean; limit?: number
}

export async function listRepairs(f: ListFilters): Promise<Repair[]> {
  let q = supabase.from('repairs').select('*')
  const or = f.q ? searchFilter(f.q) : null
  if (or) q = q.or(or)
  if (f.branchId) q = q.eq('branch_id', f.branchId)
  if (f.status) q = q.eq('status', f.status)
  if (f.manufacturerId) q = q.eq('manufacturer_id', f.manufacturerId)
  if (f.from) q = q.gte('received_on', f.from)
  if (f.to) q = q.lte('received_on', f.to)
  const { data, error } = await q.order(f.sort ?? 'updated_at', { ascending: f.asc ?? false }).limit(f.limit ?? 500)
  if (error) throw fail('一覧の取得に失敗しました')
  return data as Repair[]
}

export async function getRepair(id: string): Promise<Repair | null> {
  const { data, error } = await supabase.from('repairs').select('*').eq('id', id).maybeSingle()
  if (error) throw fail('案件の取得に失敗しました')
  return data as Repair | null
}

export async function createRepair(input: Partial<Repair>): Promise<Repair> {
  const { data, error } = await supabase.from('repairs').insert(input).select().single()
  if (error) throw fail('登録に失敗しました。入力内容と権限を確認してください')
  return data as Repair
}

/** 楽観ロック: version 一致時のみ更新。不一致なら ConflictError */
export async function updateRepair(id: string, version: number, patch: Partial<Repair>): Promise<Repair> {
  const { data, error } = await supabase.from('repairs').update(patch).eq('id', id).eq('version', version).select().maybeSingle()
  if (error) throw fail('更新に失敗しました。入力内容を確認してください')
  if (!data) throw new ConflictError()
  return data as Repair
}

export async function changeStatus(id: string, version: number, to: string, comment?: string): Promise<Repair> {
  const { data, error } = await supabase.rpc('change_status', { p_id: id, p_version: version, p_to: to, p_comment: comment ?? null })
  if (error) {
    if (error.code === '40001') throw new ConflictError()
    throw fail('ステータスを変更できません')
  }
  return data as Repair
}

export async function softDelete(id: string, version: number, restore = false): Promise<void> {
  const { error } = await supabase.rpc('soft_delete_repair', { p_id: id, p_version: version, p_restore: restore })
  if (error) { if (error.code === '40001') throw new ConflictError(); throw fail('削除/復元できません') }
}

export async function listHistory(repairId: string): Promise<HistoryRow[]> {
  const { data, error } = await supabase.from('status_history').select('*').eq('repair_id', repairId).order('changed_at')
  if (error) throw fail('履歴の取得に失敗しました')
  return data as HistoryRow[]
}

export async function serialWarnings(serial: string, branchId: number, excludeId?: string) {
  if (!serial.trim()) return { sameBranch: [] as string[], elsewhere: false }
  const { data } = await supabase.from('repairs').select('id, mgmt_no, status').eq('serial_no', serial.trim()).eq('branch_id', branchId)
  const same = (data ?? []).filter((r) => r.id !== excludeId).map((r) => r.mgmt_no as string)
  const { data: other } = await supabase.rpc('serial_exists_elsewhere', { p_serial: serial.trim() })
  return { sameBranch: same, elsewhere: Boolean(other) }
}

// ---- マスタ ----
export async function loadMasters() {
  const [b, m, d, p, s] = await Promise.all([
    supabase.from('branches').select('*').order('id'),
    supabase.from('manufacturers').select('*').order('name'),
    supabase.from('dealers').select('*').order('name'),
    supabase.from('profiles').select('*').order('display_name'),
    supabase.from('settings').select('key,value'),
  ])
  if (b.error || m.error || d.error || p.error || s.error) throw fail('マスタの取得に失敗しました')
  const settings = { ...DEFAULT_SETTINGS }
  for (const r of s.data ?? []) if (r.key in settings) (settings as Record<string, number>)[r.key] = Number(r.value)
  return { branches: b.data as Branch[], manufacturers: m.data as Named[], dealers: d.data as Dealer[], profiles: p.data as Profile[], settings: settings as Settings }
}

// ---- Edge Functions(個人情報・CSV・管理) ----
async function invoke<T>(name: string, body: unknown): Promise<T> {
  const { data, error } = await supabase.functions.invoke(name, { body: body as Record<string, unknown> })
  if (error) throw fail('処理に失敗しました。権限またはネットワークを確認してください')
  return data as T
}
export const revealPii = (repairId: string) => invoke<{ name: string | null; phone: string | null; address: string | null }>('pii-reveal', { repair_id: repairId })
export const writePii = (repairId: string, v: { name?: string; phone?: string; address?: string }) => invoke<{ ok: true }>('pii-write', { repair_id: repairId, ...v })
export const inviteUser = (v: { email: string; display_name: string; role: string; branch_id?: number | null }) => invoke<{ ok: true }>('admin-users', { action: 'invite', ...v })
export const resetMfa = (userId: string) => invoke<{ ok: true }>('admin-users', { action: 'reset_mfa', user_id: userId })

export async function exportCsv(filters: Record<string, unknown>, includePii: boolean): Promise<Blob> {
  const { data, error } = await supabase.functions.invoke('csv-export', { body: { filters, include_pii: includePii } })
  if (error) throw fail('CSV出力に失敗しました')
  // Response.text() は先頭のBOMを取り除くため、Excelで文字化けしないよう付け直す
  if (data instanceof Blob) return data
  const text = (data as string).startsWith('\uFEFF') ? (data as string) : '\uFEFF' + (data as string)
  return new Blob([text], { type: 'text/csv;charset=utf-8' })
}

// ---- ファイル ----
export async function listFiles(repairId: string): Promise<(FileRow & { url: string | null })[]> {
  const { data, error } = await supabase.from('repair_files').select('*').eq('repair_id', repairId).order('created_at')
  if (error) throw fail('ファイル一覧の取得に失敗しました')
  return Promise.all((data as FileRow[]).map(async (f) => {
    const s = await supabase.storage.from('repair-files').createSignedUrl(f.storage_path, 300)
    return { ...f, url: s.data?.signedUrl ?? null }
  }))
}

export async function uploadFile(repairId: string, file: File, userId: string, kind: 'photo' | 'attachment' = 'photo') {
  const v = validateFile(file)
  if (v) throw new Error(v)
  const sniffed = await sniffMime(file)
  if (sniffed !== file.type) throw new Error('ファイルの内容が種類と一致しません')
  const path = `${repairId}/${crypto.randomUUID()}.${extFor(file.type)}`
  const up = await supabase.storage.from('repair-files').upload(path, file, { contentType: file.type, upsert: false })
  if (up.error) throw fail('アップロードに失敗しました')
  const ins = await supabase.from('repair_files').insert({ repair_id: repairId, kind, storage_path: path, mime: file.type, size_bytes: file.size, created_by: userId })
  if (ins.error) { await supabase.storage.from('repair-files').remove([path]); throw fail('ファイル情報の保存に失敗しました') }
}

export async function deleteFile(f: FileRow) {
  await supabase.storage.from('repair-files').remove([f.storage_path])
  const { error } = await supabase.from('repair_files').delete().eq('id', f.id)
  if (error) throw fail('削除に失敗しました')
}

export async function logEvent(action: 'login' | 'logout') { await supabase.rpc('log_event', { p_action: action }) }
