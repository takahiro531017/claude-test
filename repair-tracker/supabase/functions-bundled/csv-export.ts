// csv-export: ダッシュボード貼り付け用(自動生成: scripts/bundle-functions.mjs)。直接編集しないこと。
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
function csvCell(v) {
  if (v === null || v === void 0) return "";
  let s = typeof v === "object" ? JSON.stringify(v) : String(v);
  if (/^[=+\-@\t\r]/.test(s)) s = `'${s}`;
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

// supabase/functions/csv-export/index.ts
var COLUMNS = [
  "mgmt_no",
  "branch_id",
  "received_on",
  "status",
  "priority",
  "due_on",
  "dealer_name",
  "dealer_code",
  "dealer_contact_name",
  "manufacturer_id",
  "product_name",
  "model_no",
  "serial_no",
  "purchased_on",
  "has_warranty_card",
  "in_warranty",
  "symptom",
  "maker_receipt_no",
  "maker_sent_on",
  "outbound_carrier",
  "outbound_tracking_no",
  "quote_amount",
  "quote_approved",
  "repair_detail",
  "repair_cost",
  "maker_returned_on",
  "dealer_returned_on",
  "return_carrier",
  "return_tracking_no",
  "completed_on",
  "note",
  "created_at",
  "updated_at"
];
var MAX_ROWS = 5e4;
Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders(req) });
  if (req.method !== "POST") return fail(req, 405, "POST のみ対応しています");
  const ctx = await authenticate(req);
  if (ctx instanceof Response) return ctx;
  if (!["admin", "hq_viewer", "branch_staff"].includes(ctx.role)) return fail(req, 403, "CSV出力の権限がありません");
  try {
    const b = await req.json().catch(() => ({}));
    const includePii = b.include_pii === true;
    if (includePii && ctx.role !== "admin") return fail(req, 403, "個人情報を含む出力は管理者のみ可能です");
    const f = b.filters ?? {};
    const rows = [];
    for (let from = 0; from < MAX_ROWS; from += 1e3) {
      let q = ctx.user.from("repairs").select(["id", ...COLUMNS].join(",")).order("mgmt_no").range(from, from + 999);
      if (Number.isInteger(f.branch_id)) q = q.eq("branch_id", f.branch_id);
      if (typeof f.status === "string") q = q.eq("status", f.status);
      if (typeof f.from === "string") q = q.gte("received_on", f.from);
      if (typeof f.to === "string") q = q.lte("received_on", f.to);
      const { data, error } = await q;
      if (error) throw new Error("query failed");
      rows.push(...data);
      if (data.length < 1e3) break;
    }
    const header = [...COLUMNS];
    if (includePii) header.push("enduser_name", "enduser_phone", "enduser_address");
    const lines = [header.join(",")];
    const ring = includePii ? keyRingFromEnv((k) => Deno.env.get(k)) : null;
    for (const r of rows) {
      const cells = COLUMNS.map((c) => csvCell(r[c]));
      if (includePii && ring) {
        const { data: pii } = await ctx.admin.from("repair_pii").select("name_enc, phone_enc, addr_enc").eq("repair_id", r.id).maybeSingle();
        const d = async (v, k) => v ? await decryptField(ring, v, `${r.id}:${k}`) : "";
        cells.push(csvCell(await d(pii?.name_enc, "name")), csvCell(await d(pii?.phone_enc, "phone")), csvCell(await d(pii?.addr_enc, "addr")));
      }
      lines.push(cells.join(","));
    }
    await ctx.admin.rpc("write_audit", {
      p_action: "export",
      p_repair_id: null,
      p_actor: ctx.userId,
      p_meta: { row_count: rows.length, include_pii: includePii, filters: { branch_id: f.branch_id ?? null, status: f.status ?? null, from: f.from ?? null, to: f.to ?? null } }
    });
    return new Response("\uFEFF" + lines.join("\r\n"), {
      headers: {
        ...corsHeaders(req),
        "Content-Type": "text/csv; charset=utf-8",
        "Cache-Control": "no-store",
        "Content-Disposition": 'attachment; filename="repairs.csv"'
      }
    });
  } catch {
    console.error("csv-export error");
    return fail(req, 500, "出力に失敗しました");
  }
});
