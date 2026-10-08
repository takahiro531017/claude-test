// ステータス定義・遷移・滞留判定。DB側のトリガーと同じ規則(DBが最終的な強制力を持つ)。
export type Status =
  | 'received' | 'sent_to_maker' | 'in_repair' | 'returned_from_maker' | 'returned_to_dealer' | 'completed'
  | 'on_hold' | 'quote_pending' | 'unrepairable' | 'cancelled'

export const MAIN_FLOW: Status[] = ['received', 'sent_to_maker', 'in_repair', 'returned_from_maker', 'returned_to_dealer', 'completed']
export const AUX_STATUSES: Status[] = ['on_hold', 'quote_pending', 'unrepairable', 'cancelled']
export const ALL_STATUSES: Status[] = [...MAIN_FLOW, ...AUX_STATUSES]

export const STATUS_LABEL: Record<Status, string> = {
  received: '預かり(受付)', sent_to_maker: 'メーカー発送済', in_repair: 'メーカー修理中',
  returned_from_maker: 'メーカーから返却受領', returned_to_dealer: '販売店へ返送済', completed: '完了',
  on_hold: '保留', quote_pending: '見積確認待ち', unrepairable: '修理不能・返品', cancelled: 'キャンセル',
}

// 色だけに依存しない(ラベル文字も必ず併記する)
export const STATUS_COLOR: Record<Status, string> = {
  received: '#2563eb', sent_to_maker: '#7c3aed', in_repair: '#c2410c', returned_from_maker: '#0f766e',
  returned_to_dealer: '#4d7c0f', completed: '#475569', on_hold: '#a16207', quote_pending: '#be185d',
  unrepairable: '#b91c1c', cancelled: '#6b7280',
}

export function nextStatus(s: Status): Status | null {
  const i = MAIN_FLOW.indexOf(s)
  return i >= 0 && i < MAIN_FLOW.length - 1 ? MAIN_FLOW[i + 1] : null
}
export function prevStatus(s: Status): Status | null {
  const i = MAIN_FLOW.indexOf(s)
  return i > 0 ? MAIN_FLOW[i - 1] : null
}

/** 画面に出す遷移候補(DBの transition_allowed と同等。admin は全て可) */
export function allowedTransitions(from: Status, isAdmin: boolean): Status[] {
  if (isAdmin) return ALL_STATUSES.filter((s) => s !== from)
  if (from === 'completed' || from === 'cancelled') return []
  if (from === 'unrepairable') return ['returned_to_dealer', 'completed']
  const out: Status[] = []
  const n = nextStatus(from), p = prevStatus(from)
  if (n) out.push(n)
  if (p) out.push(p)
  if (MAIN_FLOW.includes(from)) out.push(...AUX_STATUSES)
  else out.push(...MAIN_FLOW.slice(0, 5), ...AUX_STATUSES.filter((s) => s !== from)) // 補助→本流へ復帰
  return out
}

export type StaleSettings = { stale_sent_days: number; stale_return_days: number }
export type StaleInput = { status: string; maker_sent_on: string | null; maker_returned_on: string | null }

const daysBetween = (from: string, today: Date) =>
  Math.floor((Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()) - Date.parse(from)) / 86400000)

/** 滞留アラート文言(なければ null) */
export function staleReason(r: StaleInput, st: StaleSettings, today = new Date()): string | null {
  if ((r.status === 'sent_to_maker' || r.status === 'in_repair') && r.maker_sent_on) {
    const d = daysBetween(r.maker_sent_on, today)
    if (d > st.stale_sent_days) return `メーカー発送後${d}日経過`
  }
  if (r.status === 'returned_from_maker' && r.maker_returned_on) {
    const d = daysBetween(r.maker_returned_on, today)
    if (d > st.stale_return_days) return `返却受領後${d}日 販売店へ未返送`
  }
  return null
}
