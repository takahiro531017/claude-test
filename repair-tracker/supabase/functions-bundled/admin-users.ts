// admin-users: ダッシュボード貼り付け用(自動生成: scripts/bundle-functions.mjs)。直接編集しないこと。
// supabase/functions/_shared/http.ts
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.117.3";
var ALLOWED_ORIGIN = () => Deno.env.get("ALLOWED_ORIGIN") ?? "";
function corsHeaders(req) {
  const origin = req.headers.get("origin") ?? "";
  const allowed = ALLOWED_ORIGIN();
  return {
    "Access-Control-Allow-Origin": allowed && origin === allowed ? origin : "null",
    "Access-Control-Allow-Headers": "authorization, content-type, apikey",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    Vary: "Origin"
  };
}
function json(req, body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders(req), "Content-Type": "application/json", "Cache-Control": "no-store" }
  });
}
var fail = (req, status, message) => json(req, { error: message }, status);
function jwtClaims(token) {
  try {
    return JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
  } catch {
    return {};
  }
}
async function authenticate(req) {
  const authz = req.headers.get("Authorization") ?? "";
  const token = authz.replace(/^Bearer\s+/i, "");
  if (!token) return fail(req, 401, "認証が必要です");
  const url = Deno.env.get("SUPABASE_URL");
  const user = createClient(url, Deno.env.get("SUPABASE_ANON_KEY"), { global: { headers: { Authorization: `Bearer ${token}` } } });
  const admin = createClient(url, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY"));
  const { data, error } = await user.auth.getUser(token);
  if (error || !data.user) return fail(req, 401, "認証が必要です");
  if (jwtClaims(token).aal !== "aal2") return fail(req, 403, "多要素認証が必要です");
  const { data: prof } = await admin.from("profiles").select("role, branch_id, active").eq("user_id", data.user.id).single();
  if (!prof || !prof.active) return fail(req, 403, "権限がありません");
  return { userId: data.user.id, role: prof.role, branchId: prof.branch_id, admin, user };
}

// supabase/functions/_shared/validate.ts
var UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
var isUuid = (v) => typeof v === "string" && UUID.test(v);
function optString(v, max) {
  if (v === void 0 || v === null || v === "") return null;
  if (typeof v !== "string") throw new ValidationError("文字列で指定してください");
  if (v.length > max) throw new ValidationError(`${max}文字以内で入力してください`);
  return v;
}
var ValidationError = class extends Error {
};
var ROLES = ["admin", "hq_viewer", "branch_staff", "branch_viewer"];
var isRole = (v) => ROLES.includes(v);
var EMAIL = /^[^\s@]{1,64}@[^\s@]{1,255}\.[^\s@]{2,}$/;
var isEmail = (v) => typeof v === "string" && v.length <= 320 && EMAIL.test(v);

// supabase/functions/admin-users/index.ts
Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders(req) });
  if (req.method !== "POST") return fail(req, 405, "POST のみ対応しています");
  const ctx = await authenticate(req);
  if (ctx instanceof Response) return ctx;
  if (ctx.role !== "admin") return fail(req, 403, "管理者のみ実行できます");
  try {
    const b = await req.json();
    if (b.action === "invite") {
      const name = optString(b.display_name, 60);
      if (!isEmail(b.email) || !name || !isRole(b.role)) return fail(req, 400, "入力内容が不正です");
      const needsBranch = b.role === "branch_staff" || b.role === "branch_viewer";
      if (needsBranch && !Number.isInteger(b.branch_id)) return fail(req, 400, "拠点を指定してください");
      const inv = await ctx.admin.auth.admin.inviteUserByEmail(b.email, { redirectTo: Deno.env.get("SITE_URL") });
      if (inv.error || !inv.data.user) return fail(req, 400, "招待に失敗しました(既に登録済みの可能性があります)");
      const p = await ctx.admin.from("profiles").insert({
        user_id: inv.data.user.id,
        display_name: name,
        role: b.role,
        branch_id: needsBranch ? b.branch_id : null
      });
      if (p.error) {
        await ctx.admin.auth.admin.deleteUser(inv.data.user.id);
        return fail(req, 400, "招待に失敗しました");
      }
      await ctx.admin.rpc("write_audit", {
        p_action: "user_invite",
        p_repair_id: null,
        p_actor: ctx.userId,
        p_meta: { target_user: inv.data.user.id, role: b.role, branch_id: b.branch_id ?? null }
      });
      return json(req, { ok: true, user_id: inv.data.user.id });
    }
    if (b.action === "reset_mfa") {
      if (!isUuid(b.user_id)) return fail(req, 400, "ユーザーIDが不正です");
      const { data, error } = await ctx.admin.auth.admin.mfa.listFactors({ userId: b.user_id });
      if (error) return fail(req, 400, "MFAの再設定に失敗しました");
      for (const f of data.factors) await ctx.admin.auth.admin.mfa.deleteFactor({ id: f.id, userId: b.user_id });
      await ctx.admin.rpc("write_audit", { p_action: "mfa_reset", p_repair_id: null, p_actor: ctx.userId, p_meta: { target_user: b.user_id } });
      return json(req, { ok: true });
    }
    return fail(req, 400, "不明な操作です");
  } catch (e) {
    if (e instanceof ValidationError) return fail(req, 400, e.message);
    console.error("admin-users error");
    return fail(req, 500, "処理に失敗しました");
  }
});
