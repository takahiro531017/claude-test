// pii-write: ダッシュボード貼り付け用(自動生成: scripts/bundle-functions.mjs)。直接編集しないこと。
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
var b64 = (u) => btoa(String.fromCharCode(...u));
var unb64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
async function importKey(b64key) {
  const raw = unb64(b64key);
  if (raw.length !== 32) throw new Error("鍵は32バイト(AES-256)である必要があります");
  return crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt", "decrypt"]);
}
async function encryptField(ring, plain, aad) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await importKey(ring.keys[ring.current]);
  const ct = new Uint8Array(
    await crypto.subtle.encrypt({ name: "AES-GCM", iv, additionalData: new TextEncoder().encode(aad) }, key, new TextEncoder().encode(plain))
  );
  return `v${ring.current}:${b64(iv)}:${b64(ct)}`;
}

// supabase/functions/_shared/mask.ts
function maskName(name) {
  const s = name.trim();
  if (!s) return "";
  const parts = s.split(/[\s　]+/);
  if (parts.length >= 2) return `${parts[0]} ${"○".repeat(Math.min(parts.slice(1).join("").length, 4))}`;
  const chars = [...s];
  return chars[0] + "○".repeat(Math.min(chars.length - 1, 4));
}
function maskPhone(phone) {
  const d = phone.replace(/\D/g, "");
  if (d.length < 8) return "*".repeat(d.length);
  return `${d.slice(0, 3)}-****-${d.slice(-4)}`;
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

// supabase/functions/pii-write/index.ts
Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders(req) });
  if (req.method !== "POST") return fail(req, 405, "POST のみ対応しています");
  const ctx = await authenticate(req);
  if (ctx instanceof Response) return ctx;
  try {
    const b = await req.json();
    if (!isUuid(b.repair_id)) return fail(req, 400, "案件IDが不正です");
    const fields = {
      name: b.name === void 0 ? void 0 : optString(b.name, 60),
      phone: b.phone === void 0 ? void 0 : optString(b.phone, 30),
      addr: b.address === void 0 ? void 0 : optString(b.address, 200)
    };
    if (fields.phone && !/^[0-9+\-\s()]+$/.test(fields.phone)) return fail(req, 400, "電話番号の形式が不正です");
    const { data: repair } = await ctx.admin.from("repairs").select("id, branch_id, deleted_at").eq("id", b.repair_id).single();
    const allowed = ctx.role === "admin" || ctx.role === "branch_staff" && repair?.branch_id === ctx.branchId;
    if (!repair || repair.deleted_at || !allowed) return fail(req, 403, "権限がありません");
    const ring = keyRingFromEnv((k) => Deno.env.get(k));
    const aad = (f) => `${repair.id}:${f}`;
    const row = { repair_id: repair.id, key_version: Number(ring.current), updated_at: (/* @__PURE__ */ new Date()).toISOString() };
    const mask = { updated_by: ctx.userId };
    if (fields.name !== void 0) {
      row.name_enc = fields.name ? await encryptField(ring, fields.name, aad("name")) : null;
      mask.enduser_name_mask = fields.name ? maskName(fields.name) : null;
    }
    if (fields.phone !== void 0) {
      row.phone_enc = fields.phone ? await encryptField(ring, fields.phone, aad("phone")) : null;
      mask.enduser_phone_mask = fields.phone ? maskPhone(fields.phone) : null;
    }
    if (fields.addr !== void 0) row.addr_enc = fields.addr ? await encryptField(ring, fields.addr, aad("addr")) : null;
    const up = await ctx.admin.from("repair_pii").upsert(row, { onConflict: "repair_id" }).select("name_enc, phone_enc, addr_enc").single();
    if (up.error) throw new Error("save failed");
    mask.has_pii = !!(up.data.name_enc || up.data.phone_enc || up.data.addr_enc);
    const upd = await ctx.admin.from("repairs").update(mask).eq("id", repair.id);
    if (upd.error) throw new Error("save failed");
    await ctx.admin.rpc("write_audit", {
      p_action: "pii_write",
      p_repair_id: repair.id,
      p_actor: ctx.userId,
      p_meta: { fields: Object.entries(fields).filter(([, v]) => v !== void 0).map(([k]) => k) }
    });
    return json(req, { ok: true });
  } catch (e) {
    if (e instanceof ValidationError) return fail(req, 400, e.message);
    console.error("pii-write error");
    return fail(req, 500, "保存に失敗しました");
  }
});
