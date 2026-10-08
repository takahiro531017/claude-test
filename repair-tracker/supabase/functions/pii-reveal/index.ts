// 個人情報の平文表示。復号の前に必ず監査ログへ記録する(記録できなければ表示しない)。
import { authenticate, corsHeaders, fail, json } from '../_shared/http.ts'
import { decryptField, keyRingFromEnv } from '../_shared/crypto.ts'
import { isUuid } from '../_shared/validate.ts'

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: corsHeaders(req) })
  if (req.method !== 'POST') return fail(req, 405, 'POST のみ対応しています')
  const ctx = await authenticate(req)
  if (ctx instanceof Response) return ctx
  try {
    const b = await req.json()
    if (!isUuid(b.repair_id)) return fail(req, 400, '案件IDが不正です')
    const { data: repair } = await ctx.admin.from('repairs').select('id, mgmt_no, branch_id, deleted_at').eq('id', b.repair_id).single()
    // 平文を見られるのは admin と、自拠点の branch_staff のみ(hq_viewer / branch_viewer は不可)
    const allowed = ctx.role === 'admin' || (ctx.role === 'branch_staff' && repair?.branch_id === ctx.branchId)
    if (!repair || (repair.deleted_at && ctx.role !== 'admin') || !allowed) return fail(req, 403, '権限がありません')

    // 大量閲覧の抑止: 同一ユーザーが10分間に30件を超えて個人情報を表示しようとした場合は拒否
    // (アカウント乗っ取り・内部不正による一括持ち出しへの対策。上限は運用で調整可)
    const since = new Date(Date.now() - 10 * 60_000).toISOString()
    const { count } = await ctx.admin.from('audit_log').select('id', { count: 'exact', head: true })
      .eq('actor', ctx.userId).eq('action', 'pii_reveal').gte('at', since)
    if ((count ?? 0) >= 30) return fail(req, 429, '短時間に多数の個人情報を表示しました。しばらくしてからお試しください')

    const a = await ctx.admin.rpc('write_audit', {
      p_action: 'pii_reveal', p_repair_id: repair.id, p_actor: ctx.userId, p_meta: { mgmt_no: repair.mgmt_no },
    })
    if (a.error) throw new Error('audit failed')

    const { data: pii } = await ctx.admin.from('repair_pii').select('name_enc, phone_enc, addr_enc').eq('repair_id', repair.id).maybeSingle()
    const ring = keyRingFromEnv((k) => Deno.env.get(k))
    const dec = async (v: string | null | undefined, f: string) => (v ? await decryptField(ring, v, `${repair.id}:${f}`) : null)
    return json(req, {
      name: await dec(pii?.name_enc, 'name'),
      phone: await dec(pii?.phone_enc, 'phone'),
      address: await dec(pii?.addr_enc, 'addr'),
    })
  } catch {
    console.error('pii-reveal error')
    return fail(req, 500, '表示に失敗しました')
  }
})
