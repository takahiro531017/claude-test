// CSV出力。RLS が効く呼び出しユーザー権限でデータを読む(サービスキーでの全件取得はしない)。
// 個人情報列は既定で除外。含められるのは admin が明示指定した場合のみ。出力は必ず監査ログに記録。
import { authenticate, corsHeaders, fail } from '../_shared/http.ts'
import { decryptField, keyRingFromEnv } from '../_shared/crypto.ts'
import { csvCell } from '../_shared/validate.ts'

const COLUMNS = [
  'mgmt_no', 'branch_id', 'received_on', 'status', 'priority', 'due_on', 'dealer_name', 'dealer_code',
  'dealer_contact_name', 'manufacturer_id', 'product_name', 'model_no', 'serial_no', 'purchased_on',
  'has_warranty_card', 'in_warranty', 'symptom', 'maker_receipt_no', 'maker_sent_on', 'outbound_carrier',
  'outbound_tracking_no', 'quote_amount', 'quote_approved', 'repair_detail', 'repair_cost', 'maker_returned_on',
  'dealer_returned_on', 'return_carrier', 'return_tracking_no', 'completed_on', 'note', 'created_at', 'updated_at',
]
const MAX_ROWS = 50000

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: corsHeaders(req) })
  if (req.method !== 'POST') return fail(req, 405, 'POST のみ対応しています')
  const ctx = await authenticate(req)
  if (ctx instanceof Response) return ctx
  if (!['admin', 'hq_viewer', 'branch_staff'].includes(ctx.role)) return fail(req, 403, 'CSV出力の権限がありません')
  try {
    const b = await req.json().catch(() => ({}))
    const includePii = b.include_pii === true
    if (includePii && ctx.role !== 'admin') return fail(req, 403, '個人情報を含む出力は管理者のみ可能です')
    const f = b.filters ?? {}

    const rows: Record<string, unknown>[] = []
    for (let from = 0; from < MAX_ROWS; from += 1000) {
      let q = ctx.user.from('repairs').select(['id', ...COLUMNS].join(',')).order('mgmt_no').range(from, from + 999)
      if (Number.isInteger(f.branch_id)) q = q.eq('branch_id', f.branch_id)
      if (typeof f.status === 'string') q = q.eq('status', f.status)
      if (typeof f.from === 'string') q = q.gte('received_on', f.from)
      if (typeof f.to === 'string') q = q.lte('received_on', f.to)
      const { data, error } = await q
      if (error) throw new Error('query failed')
      rows.push(...(data as unknown as Record<string, unknown>[]))
      if (data.length < 1000) break
    }

    const header = [...COLUMNS]
    if (includePii) header.push('enduser_name', 'enduser_phone', 'enduser_address')
    const lines = [header.join(',')]
    const ring = includePii ? keyRingFromEnv((k) => Deno.env.get(k)) : null
    for (const r of rows) {
      const cells = COLUMNS.map((c) => csvCell(r[c]))
      if (includePii && ring) {
        const { data: pii } = await ctx.admin.from('repair_pii').select('name_enc, phone_enc, addr_enc').eq('repair_id', r.id as string).maybeSingle()
        const d = async (v: string | null | undefined, k: string) => (v ? await decryptField(ring, v, `${r.id}:${k}`) : '')
        cells.push(csvCell(await d(pii?.name_enc, 'name')), csvCell(await d(pii?.phone_enc, 'phone')), csvCell(await d(pii?.addr_enc, 'addr')))
      }
      lines.push(cells.join(','))
    }

    await ctx.admin.rpc('write_audit', {
      p_action: 'export', p_repair_id: null, p_actor: ctx.userId,
      p_meta: { row_count: rows.length, include_pii: includePii, filters: { branch_id: f.branch_id ?? null, status: f.status ?? null, from: f.from ?? null, to: f.to ?? null } },
    })
    return new Response('﻿' + lines.join('\r\n'), {
      headers: { ...corsHeaders(req), 'Content-Type': 'text/csv; charset=utf-8', 'Cache-Control': 'no-store',
        'Content-Disposition': 'attachment; filename="repairs.csv"' },
    })
  } catch {
    console.error('csv-export error')
    return fail(req, 500, '出力に失敗しました')
  }
})
