"use strict";
// 外部ライブラリ・CDN・外部通信は使わない。DOM は textContent で構築（PDF由来の文字列をHTMLとして解釈しない）。
const $ = (s) => document.querySelector(s);
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k != null) e.append(k.nodeType ? k : document.createTextNode(String(k)));
  return e;
}
const yen = (n) => (n == null ? "—" : Number(n).toLocaleString("ja-JP"));
const STATUS = { active: "有効", expiring: "期限間近", expired: "期限切れ", upcoming: "適用前", unknown: "期日不明" };
const WARN = {
  header_missing: "ヘッダー項目が読めません", header_invalid: "日付の形式が不正です", date_order: "適用期日が満期日より後です",
  region_not_found: "地帯ラベルが見つかりません", size_header_missing: "サイズ見出しが見つかりません", duplicate_cell: "セルが重複して検出されました",
  price_out_of_range: "運賃が範囲外です", weight_missing: "重量目安が読めません", notes_missing: "注記が見つかりません",
  origin_from_filename: "発地が読めずファイル名を使用しました",
};
const ERR = { not_a_pdf: "PDFではありません", size_header_not_found: "運賃マトリクス（サイズ見出し）が見つかりません。config/parser.yaml を調整してください",
  no_text_layer: "テキスト層がありません（スキャンPDFはOCR非対応）", file_too_large: "ファイルが大きすぎます", too_many_pages: "ページ数が多すぎます" };
let META = null;
const metaReady = api("/api/meta").then((m) => (META = m));

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) { let d = ""; try { d = (await r.json()).detail; } catch (_) {} throw new Error(d || r.statusText); }
  return r.json();
}
const tag = (s) => h("span", { class: "tag " + s }, STATUS[s] || s);

// ---- タブ
const loaders = { import: loadTariffs, search: initSearch, matrix: loadMatrix, combined: loadCombined, notes: loadNotes, export: () => {} };
async function show(tab) {
  await metaReady;
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll("main > section").forEach((s) => (s.hidden = s.id !== "tab-" + tab));
  loaders[tab]();
}
$("#tabs").addEventListener("click", (e) => e.target.dataset.tab && show(e.target.dataset.tab));

// ---- 取込
const drop = $("#drop");
drop.addEventListener("click", () => $("#file").click());
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); upload(e.dataTransfer.files); });
$("#file").addEventListener("change", (e) => upload(e.target.files));

async function upload(files) {
  const out = $("#import-results");
  out.replaceChildren(h("div", { class: "msg" }, "取込中…"));
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  try {
    const { results } = await api("/api/import", { method: "POST", body: fd });
    out.replaceChildren(...results.map((r) => {
      if (r.status === "error") return h("div", { class: "msg err" }, `${r.filename}: 失敗 — ${ERR[r.error] || r.error}`);
      if (r.status === "duplicate") return h("div", { class: "msg" }, `${r.filename}: 取込済みのファイルです`);
      const w = [...r.warnings.map((x) => `${WARN[x.kind] || x.kind}${x.detail ? "（" + x.detail + "）" : ""}`)];
      if (r.missing) w.push(`欠損セル ${r.missing} 件 → 「拠点別マトリクス」で手動補正できます`);
      return h("div", { class: "msg " + (w.length ? "warn" : "ok") }, `${r.filename}: ${r.origin} / ${r.cells}セル取込`, w.length ? h("ul", {}, w.map((t) => h("li", {}, t))) : null);
    }));
  } catch (e) { out.replaceChildren(h("div", { class: "msg err" }, "取込エラー: " + e.message)); }
  $("#file").value = "";
  loadTariffs();
}

async function loadTariffs() {
  const list = await api("/api/tariffs");
  const box = $("#tariff-list");
  if (!list.length) return box.replaceChildren(h("p", { class: "muted" }, "まだ取り込まれていません。"));
  box.replaceChildren(h("div", { class: "wrap" }, h("table", {},
    h("tr", {}, ["発地拠点", "状態", "適用期日", "満期日", "見積No.", "欠損", "警告", "ファイル", ""].map((t) => h("th", { class: "l" }, t))),
    list.map((t) => h("tr", {},
      h("td", {}, t.origin), h("td", { class: "l" }, tag(t.status)), h("td", { class: "l" }, t.valid_from || "?"), h("td", { class: "l" }, t.valid_to || "?"),
      h("td", { class: "l" }, t.quote_no || ""), h("td", {}, t.missing || ""), h("td", {}, t.warning_count || ""), h("td", { class: "l" }, t.filename),
      h("td", { class: "l" },
        h("button", { class: "sub", onclick: () => { pendingId = String(t.id); show("matrix"); } }, "開く"), " ",
        h("button", { class: "danger", onclick: async () => { if (confirm(`${t.origin}（${t.valid_from || "?"}）を削除しますか？`)) { await api("/api/tariffs/" + t.id, { method: "DELETE" }); loadTariffs(); } } }, "削除")))))));
}

// ---- 検索・比較
async function initSearch() {
  const [tariffs] = await Promise.all([api("/api/tariffs")]);
  const origins = [...new Set(tariffs.map((t) => t.origin))];
  $("#s-origin").replaceChildren(h("option", { value: "" }, "全拠点"), ...origins.map((o) => h("option", { value: o }, o)));
  $("#s-size").replaceChildren(h("option", { value: "" }, "全サイズ"), ...META.sizes.map((s) => h("option", { value: s }, s + (META.weight_sizes[s] ? `（〜${META.weight_sizes[s]}kg）` : ""))));
  const dl = $("#dest-list");
  if (!dl.children.length) dl.replaceChildren(...META.regions.map((r) => h("option", { value: r.name })), ...META.regions.flatMap((r) => r.prefectures.map((p) => h("option", { value: p }, r.name))), ...META.special_prefectures.map((p) => h("option", { value: p }, "別料金")));
}
$("#search-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = new URLSearchParams({ dest: $("#s-dest").value });
  if ($("#s-size").value) q.set("size", $("#s-size").value);
  if ($("#s-origin").value) q.set("origin", $("#s-origin").value);
  const d = await api("/api/lookup?" + q);
  const out = $("#search-out"), dst = d.destination;
  if (dst.special) return out.replaceChildren(h("div", { class: "msg warn" }, `${dst.prefecture}は12地帯に含まれません。沖縄は別料金です（「注記」タブで各拠点の記載を確認してください）。`));
  if (!dst.region) return out.replaceChildren(h("div", { class: "msg err" }, "着地が特定できません。地帯名または都道府県名を入力してください。"));
  const sizes = $("#s-size").value ? [Number($("#s-size").value)] : META.sizes;
  out.replaceChildren(
    h("div", { class: "msg" }, `着地: ${dst.region}` + (dst.prefecture ? `（${dst.prefecture}）` : "")),
    h("div", { class: "wrap" }, h("table", {},
      h("tr", {}, h("th", { class: "l" }, "発地拠点"), h("th", { class: "l" }, "状態"), h("th", { class: "l" }, "満期日"), sizes.map((s) => h("th", {}, s))),
      d.results.map((r) => h("tr", {}, h("td", {}, r.origin), h("td", { class: "l" }, tag(r.status)), h("td", { class: "l" }, r.valid_to || "?"),
        sizes.map((s) => {
          const p = r.prices[s], best = p != null && d.cheapest[s] === p && !["expired", "upcoming"].includes(r.status);
          return h("td", { class: best ? "best" : ["expired", "upcoming"].includes(r.status) ? "exp" : p == null ? "miss" : "" }, yen(p));
        }))))),
    h("p", { class: "muted" }, "緑=最安（税別・円）/ 灰=期限切れ・適用前（比較対象外）/ 赤=欠損"));
});

// ---- 拠点別マトリクス（手動補正）
let pendingId = null;
async function loadMatrix() {
  const list = await api("/api/tariffs");
  const sel = $("#m-select"), cur = pendingId ?? sel.value;
  pendingId = null;
  sel.replaceChildren(...list.map((t) => h("option", { value: t.id }, `${t.origin}（${t.valid_from || "?"}〜）`)));
  if (cur && list.some((t) => String(t.id) === cur)) sel.value = cur;
  if (!list.length) return $("#matrix-out").replaceChildren(h("p", { class: "muted" }, "運賃表がありません。"));
  renderMatrix(await api("/api/tariffs/" + sel.value));
}
$("#m-select").addEventListener("change", loadMatrix);

function renderMatrix(t) {
  const out = $("#matrix-out");
  const metaForm = h("form", { class: "row", onsubmit: async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    try { renderMatrix(await api("/api/tariffs/" + t.id, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(f)) })); }
    catch (err) { alert("保存できません: " + err.message); }
  } },
    ...[["origin", "発地拠点"], ["valid_from", "適用期日 (YYYY-MM-DD)"], ["valid_to", "満期日 (YYYY-MM-DD)"], ["quote_no", "見積No."], ["customer_code", "顧客コード"], ["payment_terms", "支払条件"], ["closing_day", "締日"]]
      .map(([k, lab]) => h("label", {}, lab, h("input", { name: k, value: t[k] || "" }))),
    h("button", {}, "保存"), tag(t.status));
  const msgs = [];
  if (t.missing.length) msgs.push(h("div", { class: "msg warn" }, `欠損セル ${t.missing.length} 件（赤）。セルをクリックして値を入力すると補正できます。`));
  for (const w of t.warnings) msgs.push(h("div", { class: "msg warn" }, `${WARN[w.kind] || w.kind}${w.detail ? "（" + w.detail + "）" : ""}`));
  const table = h("table", {},
    h("tr", {}, h("th", {}, "着地＼サイズ"), t.sizes.map((s) => h("th", {}, s))),
    h("tr", {}, h("th", {}, "重量目安"), t.sizes.map((s) => h("th", {}, t.weights[s] ? t.weights[s] + "kg" : ""))),
    t.regions.map((r) => h("tr", {}, h("td", {}, r), t.sizes.map((s) => {
      const c = t.rates[r][s];
      return h("td", { class: "edit " + (c ? (c.source === "manual" ? "manual" : "") : "miss"), title: c ? (c.source === "manual" ? "手動補正済み" : "") : "欠損", onclick: async () => {
        const v = prompt(`${r} / ${s}サイズの運賃（税別・円）。空欄で欠損に戻す`, c ? c.price : "");
        if (v === null) return;
        const price = v.trim() === "" ? null : Number(v.replace(/,/g, ""));
        if (price !== null && !Number.isInteger(price)) return alert("整数で入力してください");
        try { renderMatrix(await api(`/api/tariffs/${t.id}/rates`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ region: r, size: s, price }) })); }
        catch (err) { alert("保存できません: " + err.message); }
      } }, c ? yen(c.price) : "—");
    }))));
  out.replaceChildren(metaForm, ...msgs, h("div", { class: "wrap" }, table), h("p", { class: "muted" }, "黄枠=手動補正 / 赤=欠損。注記は「注記」タブ。"));
}

// ---- 統合ビュー
async function loadCombined() {
  const sel = $("#c-size");
  if (!sel.children.length) { sel.replaceChildren(...META.sizes.map((s) => h("option", { value: s }, s))); sel.value = "100"; }
  const d = await api("/api/combined");
  const size = Number(sel.value), origins = d.tariffs;
  if (!origins.length) return $("#combined-out").replaceChildren(h("p", { class: "muted" }, "運賃表がありません。"));
  const by = {}; for (const r of d.rows) by[`${r.origin}|${r.region}|${r.size}`] = r;
  $("#combined-out").replaceChildren(h("div", { class: "wrap" }, h("table", {},
    h("tr", {}, h("th", {}, "着地＼発地"), origins.map((o) => h("th", {}, o.origin, h("br"), tag(o.status))), h("th", {}, "最安")),
    META.regions.map((reg) => {
      const best = d.cheapest[`${reg.name}|${size}`];
      return h("tr", {}, h("td", {}, reg.name), origins.map((o) => {
        const r = by[`${o.origin}|${reg.name}|${size}`], inactive = ["expired", "upcoming"].includes(r.status);
        return h("td", { class: r.price == null ? "miss" : !inactive && r.price === best ? "best" : inactive ? "exp" : "" }, yen(r.price));
      }), h("td", {}, yen(best)));
    }))));
}
$("#c-size").addEventListener("change", loadCombined);

// ---- 注記
async function loadNotes() {
  const d = await api("/api/notes");
  const labels = Object.fromEntries(META.note_categories.map((c) => [c.key, c.label]));
  $("#notes-out").replaceChildren(...d.map((t) => h("div", {}, h("h2", {}, t.origin, " ", tag(t.status)),
    t.notes.length ? h("ul", { class: "notes" }, t.notes.map((n) => h("li", {}, h("b", {}, `[${labels[n.category] || "その他"}] `), n.text))) : h("p", { class: "muted" }, "注記なし"))));
  if (!d.length) $("#notes-out").replaceChildren(h("p", { class: "muted" }, "運賃表がありません。"));
}

metaReady.then(loadTariffs);
