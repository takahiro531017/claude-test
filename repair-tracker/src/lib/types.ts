import type { Status } from './status'

export type Role = 'admin' | 'hq_viewer' | 'branch_staff' | 'branch_viewer'
export const ROLE_LABEL: Record<Role, string> = {
  admin: '管理者(本社情シス)', hq_viewer: '本社閲覧', branch_staff: '拠点担当', branch_viewer: '拠点閲覧',
}
export type Profile = { user_id: string; display_name: string; role: Role; branch_id: number | null; active: boolean }
export type Branch = { id: number; code: string; name: string; active: boolean }
export type Named = { id: number; name: string; active: boolean }
export type Dealer = { id: number; code: string; name: string; active: boolean }

export type Repair = {
  id: string; mgmt_no: string; branch_id: number; received_on: string; status: Status; priority: 'normal' | 'urgent'
  due_on: string | null; dealer_id: number | null; dealer_name: string; dealer_code: string | null
  dealer_contact_name: string | null; dealer_contact: string | null; manufacturer_id: number
  product_name: string; model_no: string | null; serial_no: string | null; purchased_on: string | null
  has_warranty_card: boolean; in_warranty: boolean | null; accessories: string[]; symptom: string
  appearance_note: string | null; enduser_name_mask: string | null; enduser_phone_mask: string | null; has_pii: boolean
  maker_receipt_no: string | null; maker_sent_on: string | null; outbound_carrier: string | null
  outbound_tracking_no: string | null; quote_amount: number | null; quote_approved: boolean | null
  repair_detail: string | null; repair_cost: number | null; maker_returned_on: string | null
  dealer_returned_on: string | null; return_carrier: string | null; return_tracking_no: string | null
  completed_on: string | null; note: string | null; version: number; created_by: string | null
  created_at: string; updated_by: string | null; updated_at: string; deleted_at: string | null; pii_purged_at: string | null
}

export type HistoryRow = { id: number; from_status: string | null; to_status: string; changed_by: string | null; changed_at: string; comment: string | null }
export type FileRow = { id: string; kind: string; storage_path: string; mime: string; size_bytes: number; created_at: string }
export type Settings = { stale_sent_days: number; stale_return_days: number; retention_years: number; session_timeout_min: number }
export const DEFAULT_SETTINGS: Settings = { stale_sent_days: 14, stale_return_days: 7, retention_years: 3, session_timeout_min: 30 }

export const ACCESSORY_CHOICES = ['リモコン', '電源コード', '取扱説明書', '保証書', '付属ケーブル', '元箱', 'フィルター', 'その他']
export const CARRIERS = ['ヤマト運輸', '佐川急便', '日本郵便', '西濃運輸', '福山通運', '自社便', 'その他']
