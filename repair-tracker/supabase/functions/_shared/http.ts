// 共通: CORS・認証(JWT + MFA aal2 必須)・エラー応答
import { createClient, type SupabaseClient } from 'https://esm.sh/@supabase/supabase-js@2.45.4'
import type { Role } from './validate.ts'

export const ALLOWED_ORIGIN = () => Deno.env.get('ALLOWED_ORIGIN') ?? ''

export function corsHeaders(req: Request): Record<string, string> {
  const origin = req.headers.get('origin') ?? ''
  const allowed = ALLOWED_ORIGIN()
  return {
    'Access-Control-Allow-Origin': allowed && origin === allowed ? origin : 'null',
    'Access-Control-Allow-Headers': 'authorization, content-type, apikey',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    Vary: 'Origin',
  }
}

export function json(req: Request, body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders(req), 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
  })
}
/** エラー本文には個人情報・内部詳細を含めない */
export const fail = (req: Request, status: number, message: string) => json(req, { error: message }, status)

export type Ctx = {
  userId: string
  role: Role
  branchId: number | null
  admin: SupabaseClient // service_role(権限確認後のみ使用)
  user: SupabaseClient  // 呼び出しユーザーの権限(RLS適用)
}

function jwtClaims(token: string): Record<string, unknown> {
  try { return JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))) } catch { return {} }
}

export async function authenticate(req: Request): Promise<Ctx | Response> {
  const authz = req.headers.get('Authorization') ?? ''
  const token = authz.replace(/^Bearer\s+/i, '')
  if (!token) return fail(req, 401, '認証が必要です')
  const url = Deno.env.get('SUPABASE_URL')!
  const user = createClient(url, Deno.env.get('SUPABASE_ANON_KEY')!, { global: { headers: { Authorization: `Bearer ${token}` } } })
  const admin = createClient(url, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!)
  const { data, error } = await user.auth.getUser(token)
  if (error || !data.user) return fail(req, 401, '認証が必要です')
  // 多要素認証(TOTP)を通過したセッションのみ許可
  if (jwtClaims(token).aal !== 'aal2') return fail(req, 403, '多要素認証が必要です')
  const { data: prof } = await admin.from('profiles').select('role, branch_id, active').eq('user_id', data.user.id).single()
  if (!prof || !prof.active) return fail(req, 403, '権限がありません')
  return { userId: data.user.id, role: prof.role as Role, branchId: prof.branch_id, admin, user }
}
