// エンドユーザー個人情報の暗号化保存。平文はこの関数内のメモリにのみ存在し、ログに出さない。
import { authenticate, corsHeaders, fail, json } from '../_shared/http.ts'
import { encryptField, keyRingFromEnv } from '../_shared/crypto.ts'
import { maskName, maskPhone } from '../_shared/mask.ts'
import { isUuid, optString, ValidationError } from '../_shared/validate.ts'

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: corsHeaders(req) })
  if (req.method !== 'POST') return fail(req, 405, 'POST のみ対応しています')
  const ctx = await authenticate(req)
  if (ctx instanceof Response) return ctx
  try {
    const b = await req.json()
    if (!isUuid(b.repair_id)) return fail(req, 400, '案件IDが不正です')
    // undefined = 変更なし / '' = 削除 / 文字列 = 置換
    const fields = {
      name: b.name === undefined ? undefined : optString(b.name, 60),
      phone: b.phone === undefined ? undefined : optString(b.phone, 30),
      addr: b.address === undefined ? undefined : optString(b.address, 200),
    }
    if (fields.phone && !/^[0-9+\-\s()]+$/.test(fields.phone)) return fail(req, 400, '電話番号の形式が不正です')

    const { data: repair } = await ctx.admin.from('repairs').select('id, branch_id, deleted_at').eq('id', b.repair_id).single()
    const allowed = ctx.role === 'admin' || (ctx.role === 'branch_staff' && repair?.branch_id === ctx.branchId)
    if (!repair || repair.deleted_at || !allowed) return fail(req, 403, '権限がありません')

    const ring = keyRingFromEnv((k) => Deno.env.get(k))
    const aad = (f: string) => `${repair.id}:${f}`
    const row: Record<string, unknown> = { repair_id: repair.id, key_version: Number(ring.current), updated_at: new Date().toISOString() }
    const mask: Record<string, unknown> = { updated_by: ctx.userId }
    if (fields.name !== undefined) {
      row.name_enc = fields.name ? await encryptField(ring, fields.name, aad('name')) : null
      mask.enduser_name_mask = fields.name ? maskName(fields.name) : null
    }
    if (fields.phone !== undefined) {
      row.phone_enc = fields.phone ? await encryptField(ring, fields.phone, aad('phone')) : null
      mask.enduser_phone_mask = fields.phone ? maskPhone(fields.phone) : null
    }
    if (fields.addr !== undefined) row.addr_enc = fields.addr ? await encryptField(ring, fields.addr, aad('addr')) : null

    const up = await ctx.admin.from('repair_pii').upsert(row, { onConflict: 'repair_id' }).select('name_enc, phone_enc, addr_enc').single()
    if (up.error) throw new Error('save failed')
    mask.has_pii = !!(up.data.name_enc || up.data.phone_enc || up.data.addr_enc)
    const upd = await ctx.admin.from('repairs').update(mask).eq('id', repair.id)
    if (upd.error) throw new Error('save failed')
    // 監査ログには「どの項目を更新したか」のみ記録(値は記録しない)
    await ctx.admin.rpc('write_audit', {
      p_action: 'pii_write', p_repair_id: repair.id, p_actor: ctx.userId,
      p_meta: { fields: Object.entries(fields).filter(([, v]) => v !== undefined).map(([k]) => k) },
    })
    return json(req, { ok: true })
  } catch (e) {
    if (e instanceof ValidationError) return fail(req, 400, e.message)
    console.error('pii-write error') // 例外内容にも個人情報が含まれ得るため出力しない
    return fail(req, 500, '保存に失敗しました')
  }
})
