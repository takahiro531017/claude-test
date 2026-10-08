// 一覧画面用のマスク値(DBにはマスク済みの値のみ保存。平文は保存しない)

/** 「山田 太郎」→「山田 ○○」/ 空白なし「山田太郎」→「山○○○」 */
export function maskName(name: string): string {
  const s = name.trim()
  if (!s) return ''
  const parts = s.split(/[\s　]+/)
  if (parts.length >= 2) return `${parts[0]} ${'○'.repeat(Math.min(parts.slice(1).join('').length, 4))}`
  const chars = [...s]
  return chars[0] + '○'.repeat(Math.min(chars.length - 1, 4))
}

/** 「09012345678」→「090-****-5678」 */
export function maskPhone(phone: string): string {
  const d = phone.replace(/\D/g, '')
  if (d.length < 8) return '*'.repeat(d.length)
  return `${d.slice(0, 3)}-****-${d.slice(-4)}`
}
