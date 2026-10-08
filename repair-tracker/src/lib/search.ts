// PostgREST の or() フィルタを壊す/注入に使われ得る文字を除去する
export function sanitizeSearch(q: string): string {
  return q.replace(/[,()*%_\\"'`;:]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 60)
}
export const SEARCH_COLUMNS = ['mgmt_no', 'dealer_name', 'model_no', 'serial_no', 'outbound_tracking_no', 'return_tracking_no', 'maker_receipt_no']
export function searchFilter(q: string): string | null {
  const s = sanitizeSearch(q)
  return s ? SEARCH_COLUMNS.map((c) => `${c}.ilike.%${s}%`).join(',') : null
}
