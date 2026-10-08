// サーバー側入力検証(クライアント側の検証だけに頼らない)
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
export const isUuid = (v: unknown): v is string => typeof v === 'string' && UUID.test(v)

export function optString(v: unknown, max: number): string | null {
  if (v === undefined || v === null || v === '') return null
  if (typeof v !== 'string') throw new ValidationError('文字列で指定してください')
  if (v.length > max) throw new ValidationError(`${max}文字以内で入力してください`)
  return v
}

export class ValidationError extends Error {}

export const ROLES = ['admin', 'hq_viewer', 'branch_staff', 'branch_viewer'] as const
export type Role = (typeof ROLES)[number]
export const isRole = (v: unknown): v is Role => (ROLES as readonly string[]).includes(v as string)

const EMAIL = /^[^\s@]{1,64}@[^\s@]{1,255}\.[^\s@]{2,}$/
export const isEmail = (v: unknown): v is string => typeof v === 'string' && v.length <= 320 && EMAIL.test(v)

/** CSV数式インジェクション対策: 先頭が = + - @ タブ CR の値は ' を付ける */
export function csvCell(v: unknown): string {
  if (v === null || v === undefined) return ''
  let s = typeof v === 'object' ? JSON.stringify(v) : String(v)
  if (/^[=+\-@\t\r]/.test(s)) s = `'${s}`
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}
