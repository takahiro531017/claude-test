// 管理者専用: ユーザー招待・MFA再設定(自己登録は不可。招待のみ)
import { authenticate, corsHeaders, fail, json } from '../_shared/http.ts'
import { isEmail, isRole, isUuid, optString, ValidationError } from '../_shared/validate.ts'

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: corsHeaders(req) })
  if (req.method !== 'POST') return fail(req, 405, 'POST のみ対応しています')
  const ctx = await authenticate(req)
  if (ctx instanceof Response) return ctx
  if (ctx.role !== 'admin') return fail(req, 403, '管理者のみ実行できます')
  try {
    const b = await req.json()
    if (b.action === 'invite') {
      const name = optString(b.display_name, 60)
      if (!isEmail(b.email) || !name || !isRole(b.role)) return fail(req, 400, '入力内容が不正です')
      const needsBranch = b.role === 'branch_staff' || b.role === 'branch_viewer'
      if (needsBranch && !Number.isInteger(b.branch_id)) return fail(req, 400, '拠点を指定してください')
      const inv = await ctx.admin.auth.admin.inviteUserByEmail(b.email, { redirectTo: Deno.env.get('SITE_URL') })
      if (inv.error || !inv.data.user) return fail(req, 400, '招待に失敗しました(既に登録済みの可能性があります)')
      const p = await ctx.admin.from('profiles').insert({
        user_id: inv.data.user.id, display_name: name, role: b.role, branch_id: needsBranch ? b.branch_id : null,
      })
      if (p.error) { await ctx.admin.auth.admin.deleteUser(inv.data.user.id); return fail(req, 400, '招待に失敗しました') }
      await ctx.admin.rpc('write_audit', { p_action: 'user_invite', p_repair_id: null, p_actor: ctx.userId,
        p_meta: { target_user: inv.data.user.id, role: b.role, branch_id: b.branch_id ?? null } })
      return json(req, { ok: true, user_id: inv.data.user.id })
    }
    if (b.action === 'reset_mfa') {
      if (!isUuid(b.user_id)) return fail(req, 400, 'ユーザーIDが不正です')
      const { data, error } = await ctx.admin.auth.admin.mfa.listFactors({ userId: b.user_id })
      if (error) return fail(req, 400, 'MFAの再設定に失敗しました')
      for (const f of data.factors) await ctx.admin.auth.admin.mfa.deleteFactor({ id: f.id, userId: b.user_id })
      await ctx.admin.rpc('write_audit', { p_action: 'mfa_reset', p_repair_id: null, p_actor: ctx.userId, p_meta: { target_user: b.user_id } })
      return json(req, { ok: true })
    }
    return fail(req, 400, '不明な操作です')
  } catch (e) {
    if (e instanceof ValidationError) return fail(req, 400, e.message)
    console.error('admin-users error')
    return fail(req, 500, '処理に失敗しました')
  }
})
