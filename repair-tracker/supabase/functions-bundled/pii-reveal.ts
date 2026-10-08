// pii-reveal: ダッシュボード貼り付け用(自動生成: scripts/bundle-functions.mjs)。直接編集しないこと。
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

// supabase/functions/_shared/crypto.ts
function keyRingFromEnv(get) {
  const raw = get("PII_KEYS");
  const current = get("PII_KEY_CURRENT");
  if (!raw || !current) throw new Error("暗号鍵が設定されていません");
  const keys = JSON.parse(raw);
  if (!keys[current]) throw new Error("現在の鍵番号に対応する鍵がありません");
  return { keys, current };
}
var unb64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
async function importKey(b64key) {
  const raw = unb64(b64key);
  if (raw.length !== 32) throw new Error("鍵は32バイト(AES-256)である必要があります");
  return crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt", "decrypt"]);
}
async function decryptField(ring, stored, aad) {
  const m = /^v(\d+):([A-Za-z0-9+/=]+):([A-Za-z0-9+/=]+)$/.exec(stored);
  if (!m) throw new Error("暗号文の形式が不正です");
  const k = ring.keys[m[1]];
  if (!k) throw new Error("該当する鍵がありません");
  const key = await importKey(k);
  const pt = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: unb64(m[2]), additionalData: new TextEncoder().encode(aad) },
    key,
    unb64(m[3])
  );
  return new TextDecoder().decode(pt);
}

// supabase/functions/_shared/validate.ts
var UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
var isUuid = (v) => typeof v === "string" && UUID.test(v);

// supabase/functions/pii-reveal/index.ts
Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders(req) });
  if (req.method !== "POST") return fail(req, 405, "POST のみ対応しています");
  const ctx = await authenticate(req);
  if (ctx instanceof Response) return ctx;
  try {
    const b = await req.json();
    if (!isUuid(b.repair_id)) return fail(req, 400, "案件IDが不正です");
    const { data: repair } = await ctx.admin.from("repairs").select("id, mgmt_no, branch_id, deleted_at").eq("id", b.repair_id).single();
    const allowed = ctx.role === "admin" || ctx.role === "branch_staff" && repair?.branch_id === ctx.branchId;
    if (!repair || repair.deleted_at && ctx.role !== "admin" || !allowed) return fail(req, 403, "権限がありません");
    const since = new Date(Date.now() - 10 * 6e4).toISOString();
    const { count } = await ctx.admin.from("audit_log").select("id", { count: "exact", head: true }).eq("actor", ctx.userId).eq("action", "pii_reveal").gte("at", since);
    if ((count ?? 0) >= 30) return fail(req, 429, "短時間に多数の個人情報を表示しました。しばらくしてからお試しください");
    const a = await ctx.admin.rpc("write_audit", {
      p_action: "pii_reveal",
      p_repair_id: repair.id,
      p_actor: ctx.userId,
      p_meta: { mgmt_no: repair.mgmt_no }
    });
    if (a.error) throw new Error("audit failed");
    const { data: pii } = await ctx.admin.from("repair_pii").select("name_enc, phone_enc, addr_enc").eq("repair_id", repair.id).maybeSingle();
    const ring = keyRingFromEnv((k) => Deno.env.get(k));
    const dec = async (v, f) => v ? await decryptField(ring, v, `${repair.id}:${f}`) : null;
    return json(req, {
      name: await dec(pii?.name_enc, "name"),
      phone: await dec(pii?.phone_enc, "phone"),
      address: await dec(pii?.addr_enc, "addr")
    });
  } catch {
    console.error("pii-reveal error");
    return fail(req, 500, "表示に失敗しました");
  }
});
