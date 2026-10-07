"use strict";
/* 営業訪問管理 フロント。外部ライブラリ・外部通信なし(同一オリジンの /api/ のみ)。 */
const $app = document.getElementById("app");
const S = { me: null, meta: null };

// ---------- ユーティリティ ----------
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtDate = (iso) => (iso ? iso.slice(0, 4) + "/" + iso.slice(5, 7) + "/" + iso.slice(8, 10) : "");
const fmtMonth = (ym) => ym.slice(0, 4) + "年" + Number(ym.slice(5, 7)) + "月";
const pct = (r) => (r * 100).toFixed(1) + "%";
const addMonths = (ym, n) => { const i = Number(ym.slice(0, 4)) * 12 + Number(ym.slice(5, 7)) - 1 + n; return String(Math.floor(i / 12)).padStart(4, "0") + "-" + String(i % 12 + 1).padStart(2, "0"); };
const qs = (o) => { const p = new URLSearchParams(); Object.entries(o).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") p.set(k, v); }); const s = p.toString(); return s ? "?" + s : ""; };
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

let toastTimer;
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove("show"), 2600);
}

async function api(path, opt = {}) {
  const o = { credentials: "same-origin", headers: {}, ...opt };
  if (opt.json !== undefined) { o.method = opt.method || "POST"; o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(opt.json); delete o.json; }
  let r;
  try { r = await fetch(path, o); } catch { const e = new Error("サーバーに接続できません。ネットワークを確認してください"); throw e; }
  let data = null; try { data = await r.json(); } catch { /* CSV等 */ }
  if (!r.ok) {
    const d = data && data.detail;
    const e = new Error(typeof d === "string" ? d : (d && d.message) || `エラーが発生しました (${r.status})`);
    e.status = r.status; e.code = d && d.code;
    if (r.status === 401 && !path.startsWith("/api/auth/login")) { S.me = null; e.handled = true; renderLogin(); }
    if (r.status === 403 && e.code === "must_change") { e.handled = true; renderChangePw(true); }
    throw e;
  }
  return data;
}

const loading = () => `<div class="center-msg"><span class="spin"></span><div>読み込み中…</div></div>`;
const errBox = (e) => `<div class="alert err">${esc(e.message)} <button class="btn sm" data-retry>再読み込み</button></div>`;
function fail(el, e, retry) {
  if (e.handled) return;
  el.innerHTML = errBox(e);
  const b = $("[data-retry]", el); if (b) b.onclick = retry;
}

function confirmBox(message, okLabel = "OK", danger = false) {
  return new Promise((resolve) => {
    const bg = document.createElement("div");
    bg.className = "modal-bg"; bg.setAttribute("role", "dialog"); bg.setAttribute("aria-modal", "true");
    bg.innerHTML = `<div class="modal"><div>${esc(message)}</div><div class="row"><button class="btn" data-n>キャンセル</button><button class="btn ${danger ? "danger" : "pri"}" data-y>${esc(okLabel)}</button></div></div>`;
    document.body.appendChild(bg);
    const done = (v) => { bg.remove(); resolve(v); };
    $("[data-n]", bg).onclick = () => done(false); $("[data-y]", bg).onclick = () => done(true);
    bg.onclick = (ev) => { if (ev.target === bg) done(false); };
    $("[data-y]", bg).focus();
  });
}
function infoBox(html) {
  const bg = document.createElement("div");
  bg.className = "modal-bg"; bg.innerHTML = `<div class="modal">${html}<div class="row"><button class="btn pri" data-c>閉じる</button></div></div>`;
  document.body.appendChild(bg); $("[data-c]", bg).onclick = () => bg.remove();
}

function elapsedBadge(s) {
  if (s.days === null || s.days === undefined) return `<span class="badge b-gray">未訪問</span>`;
  const th = S.meta.threshold_days;
  const cls = s.days >= th ? "b-red" : s.days >= th / 2 ? "b-amber" : "b-green";
  return `<span class="badge ${cls}">${s.days}日前</span>`;
}
const overCls = (s) => (s.days === null ? "none" : s.days >= S.meta.threshold_days ? "over" : "");

// ---------- 認証画面 ----------
function renderLogin() {
  $app.innerHTML = `<div class="login"><h1>営業訪問管理</h1><form class="card" id="f" autocomplete="on">
    <label class="f" for="id">ID(営業コード)</label><input id="id" name="username" autocomplete="username" autocapitalize="off" required>
    <label class="f" for="pw">パスワード</label><input id="pw" name="password" type="password" autocomplete="current-password" required>
    <div id="msg"></div><div style="margin-top:14px"><button class="btn pri block" type="submit">ログイン</button></div></form>
    <p class="muted small">社内ネットワーク専用です。</p></div>`;
  $("#id").focus();
  $("#f").onsubmit = async (ev) => {
    ev.preventDefault(); const b = $("button", ev.target); b.disabled = true;
    try {
      S.me = await api("/api/auth/login", { json: { id: $("#id").value.trim(), password: $("#pw").value } });
      if (S.me.must_change) return renderChangePw(true);
      await boot();
    } catch (e) { $("#msg").innerHTML = `<div class="alert err">${esc(e.message)}</div>`; b.disabled = false; }
  };
}

function renderChangePw(forced) {
  $app.innerHTML = `<div class="login"><h1>パスワードの変更</h1><form class="card" id="f">
    ${forced ? `<div class="alert warn">初回ログインのため、新しいパスワードを設定してください。</div>` : ""}
    <label class="f" for="o">現在のパスワード</label><input id="o" type="password" autocomplete="current-password" required>
    <label class="f" for="n">新しいパスワード(8文字以上・英字と数字を含む)</label><input id="n" type="password" autocomplete="new-password" required>
    <label class="f" for="n2">新しいパスワード(確認)</label><input id="n2" type="password" autocomplete="new-password" required>
    <div id="msg"></div><div style="margin-top:14px"><button class="btn pri block" type="submit">変更する</button></div></form></div>`;
  $("#f").onsubmit = async (ev) => {
    ev.preventDefault();
    if ($("#n").value !== $("#n2").value) return ($("#msg").innerHTML = `<div class="alert err">確認用パスワードが一致しません</div>`);
    try {
      await api("/api/auth/change-password", { json: { old_password: $("#o").value, new_password: $("#n").value } });
      toast("パスワードを変更しました"); await boot();
    } catch (e) { if (!e.handled) $("#msg").innerHTML = `<div class="alert err">${esc(e.message)}</div>`; }
  };
}

// ---------- シェル ----------
const NAV = [["/", "ホーム", "⌂"], ["/visit", "訪問入力", "＋", "fab"], ["/stores", "店舗", "▤"], ["/stats", "集計", "▥"]];
function shell() {
  const admin = S.me.role === "admin";
  const links = (cls) => NAV.map(([h, l, ic, f]) => `<a href="#${h}" data-nav="${h}" class="${f || ""}"><span class="ic">${ic}</span><span>${l}</span></a>`).join("")
    + (cls === "side" && admin ? `<a href="#/admin" data-nav="/admin"><span class="ic">⚙</span><span>管理</span></a>` : "");
  $app.innerHTML = `<div class="shell"><nav class="side" aria-label="メニュー"><div class="brand">営業訪問管理</div>${links("side")}<div class="grow"></div>
    <a href="#/password"><span class="ic">🔑</span><span>パスワード変更</span></a><a href="#" id="logout"><span class="ic">⎋</span><span>ログアウト</span></a></nav>
    <main class="main"><div class="topbar"><span>${esc(S.me.name)}(${S.me.role === "admin" ? "管理者" : "営業"})</span><span class="row">
    ${admin ? `<a class="btn sm" href="#/admin">管理</a>` : ""}<a class="btn sm" href="#/password">PW変更</a><button class="btn sm" id="logout2">ログアウト</button></span></div>
    <div id="view"></div></main><nav class="bottom-nav" aria-label="メニュー">${links("bottom")}</nav></div>`;
  const out = async (ev) => { ev.preventDefault(); try { await api("/api/auth/logout", { method: "POST" }); } catch { /* noop */ } S.me = null; renderLogin(); };
  $("#logout").onclick = out; $("#logout2").onclick = out;
}
function markNav(path) {
  const key = path.startsWith("/store") ? "/stores" : path.startsWith("/visit") ? "/visit" : path.startsWith("/stats") ? "/stats" : path.startsWith("/admin") ? "/admin" : "/";
  $$("[data-nav]").forEach((a) => a.classList.toggle("on", a.dataset.nav === key));
}

// ---------- ルーター ----------
async function route() {
  if (!S.me) return;
  if (!$("#view")) shell();
  const h = location.hash.slice(1) || "/"; const [path, query] = h.split("?");
  const q = Object.fromEntries(new URLSearchParams(query || ""));
  markNav(path); window.scrollTo(0, 0);
  const el = $("#view"); el.innerHTML = loading();
  const run = async () => {
    try {
      let m;
      if (path === "/") await vHome(el);
      else if (path === "/visit") await vVisit(el, q);
      else if (path === "/stores") await vStores(el);
      else if ((m = path.match(/^\/store\/(.+)$/))) await vStoreDetail(el, decodeURIComponent(m[1]));
      else if (path === "/stats" || path === "/stats/monthly") await vMonthly(el, q);
      else if (path === "/stats/rep") await vByRep(el, q);
      else if ((m = path.match(/^\/stats\/rep\/(.+)$/))) await vRepDetail(el, decodeURIComponent(m[1]), q);
      else if (path === "/admin") await vAdmin(el);
      else if (path === "/password") { renderChangePw(false); }
      else el.innerHTML = `<div class="empty">ページが見つかりません</div>`;
    } catch (e) { fail(el, e, run); }
  };
  run();
}
window.addEventListener("hashchange", route);

async function boot() {
  try {
    S.me = await api("/api/auth/me");
    if (S.me.must_change) return renderChangePw(true);
    S.meta = await api("/api/meta");
    $app.innerHTML = ""; if (!location.hash) location.hash = "#/";
    route();
  } catch (e) { if (!e.handled) { $app.innerHTML = `<div class="login">${errBox(e)}</div>`; const b = $("[data-retry]"); if (b) b.onclick = boot; } }
}

// ---------- ホーム ----------
const kpi = (v, l) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`;
function kpiRow(s) {
  return `<div class="kpis">${kpi(s.visits, "訪問回数")}${kpi(s.stores, "訪問した店舗数")}${kpi(s.companies, "訪問した法人数")}${kpi(pct(s.rate), `訪問済み割合(${s.visited_assigned}/${s.assigned_stores})`)}</div>`;
}
function storeItem(s) {
  return `<a class="item ${overCls(s)}" href="#/store/${encodeURIComponent(s.code)}"><div><div class="t">${esc(s.display_name)}</div>
  <div class="muted small">${esc(s.company)}${s.name ? "" : ""} ・ ${esc(s.code)} ・ ${esc(s.rep_name || "")}</div></div>
  <div class="r">${elapsedBadge(s)}<div class="muted small">${s.last_visit ? fmtDate(s.last_visit) : ""}</div></div></a>`;
}
async function vHome(el) {
  const me = S.me, rep = me.rep_code || "";
  const ym = S.meta.today.slice(0, 7);
  const [m, vis, over] = await Promise.all([
    api("/api/stats/monthly" + qs({ month: ym, rep })),
    api("/api/visits" + qs({ limit: 5, rep })),
    api("/api/stores" + qs({ min_days: S.meta.threshold_days, rep, sort: "days", order: "desc", limit: 5 }))]);
  el.innerHTML = `<h1>ホーム</h1><a class="btn pri block" href="#/visit">＋ 訪問を入力する</a>
    <h2>${fmtMonth(ym)}の${rep ? "あなたの" : "全体の"}実績</h2>${kpiRow(m.summary)}
    <h2>${S.meta.threshold_days}日以上 未訪問の${rep ? "担当" : ""}店舗(上位5件)</h2>
    <div class="list">${over.items.length ? over.items.map(storeItem).join("") : `<div class="empty">該当する店舗はありません 👍</div>`}</div>
    ${over.items.length ? `<p><a href="#/stores">店舗一覧で見る →</a></p>` : ""}
    <h2>最近の訪問${rep ? "(自分)" : ""}</h2>
    <div class="list">${vis.items.length ? vis.items.map((v) => `<div class="item"><div><div class="t">${esc(v.display_name)}</div><div class="muted small">${esc(v.rep_name || "")}${v.memo ? " ・ " + esc(v.memo) : ""}</div></div><div class="r">${fmtDate(v.visit_date)}</div></div>`).join("") : `<div class="empty">まだ訪問の記録がありません</div>`}</div>`;
}

// ---------- 訪問入力 ----------
async function vVisit(el, q) {
  const me = S.me, isAdmin = me.role === "admin";
  let store = null, editing = null, seq = 0, cq = "", sq = "";
  if (q.store) { try { const d = await api("/api/stores/" + encodeURIComponent(q.store)); store = d.store; } catch (e) { if (e.handled) return; } }
  el.innerHTML = `<h1 id="ttl">訪問を入力</h1><form class="card" id="f">
    <label class="f" for="d">訪問日</label><input id="d" type="date" required>
    <label class="f" for="r">営業担当者</label><select id="r" ${isAdmin ? "" : "disabled"}>${S.meta.reps.map((r) => `<option value="${esc(r.code)}">${esc(r.name)}(${esc(r.code)})</option>`).join("")}</select>
    <label class="f">店舗</label><div id="sbox"></div>
    <label class="f" for="m">メモ(任意)</label><textarea id="m" maxlength="1000" placeholder="例: 新商品の案内"></textarea>
    <div id="msg"></div><div class="row" style="margin-top:14px"><button class="btn pri block grow" id="go" type="submit">登録する</button><button class="btn" type="button" id="cancel" hidden>編集をやめる</button></div></form>
    <h2>${isAdmin ? "最近の訪問(全員)" : "最近の自分の訪問"}</h2><div id="recent">${loading()}</div>`;
  const $d = $("#d"), $r = $("#r"), $m = $("#m");
  $d.value = S.meta.today;
  if (me.rep_code) $r.value = me.rep_code; else if (S.meta.reps[0]) $r.value = S.meta.reps[0].code;

  function renderStore() {
    const box = $("#sbox");
    if (store) {
      box.innerHTML = `<div class="sel"><div><div class="t">${esc(store.display_name)}</div><div class="muted small">${esc(store.company)} ・ ${esc(store.code)}</div></div><button type="button" class="btn sm" id="chg">変更</button></div>`;
      $("#chg").onclick = () => { store = null; renderStore(); };
    } else {
      box.innerHTML = `<input id="cq" type="search" list="colist" placeholder="① 法人名で絞り込み(例: ヤマダ)" autocomplete="off" aria-label="法人名で絞り込み" value="${esc(cq)}"><datalist id="colist">${S.meta.companies.map((c) => `<option value="${esc(c)}">`).join("")}</datalist>
        <input id="sq" type="search" inputmode="search" placeholder="② 店舗名・コードで検索" autocomplete="off" aria-label="店舗名またはコードで検索" style="margin-top:8px" value="${esc(sq)}"><div class="pick list" id="pick"></div>`;
      const run = async () => {
        const my = ++seq; const pick = $("#pick"); pick.innerHTML = `<div class="empty"><span class="spin"></span></div>`;
        try {
          const d = await api("/api/stores" + qs({ q: $("#sq").value, company_q: $("#cq").value, mine_first: 1, limit: 30, sort: "company", order: "asc" }));
          if (my !== seq) return;
          pick.innerHTML = d.items.length ? d.items.map((s) => `<button type="button" class="item" data-c="${esc(s.code)}"><div><div class="t">${esc(s.display_name)}</div><div class="muted small">${esc(s.company)} ・ ${esc(s.code)}${s.rep_code === me.rep_code ? " ・ <b>担当</b>" : ""}</div></div><div class="r">${elapsedBadge(s)}</div></button>`).join("") : `<div class="empty">該当する店舗がありません</div>`;
          $$("[data-c]", pick).forEach((b) => (b.onclick = () => { store = d.items.find((x) => x.code === b.dataset.c); renderStore(); }));
        } catch (e) { if (!e.handled) pick.innerHTML = errBox(e); }
      };
      let t; const inp = () => { cq = $("#cq").value; sq = $("#sq").value; clearTimeout(t); t = setTimeout(run, 200); };
      $("#sq").oninput = inp; $("#cq").oninput = inp; $("#cq").onchange = inp;
      run();
    }
  }
  renderStore();

  async function loadRecent() {
    const box = $("#recent");
    try {
      const d = await api("/api/visits" + qs({ limit: 10, rep: isAdmin ? "" : me.rep_code }));
      box.innerHTML = d.items.length ? `<div class="list">${d.items.map((v) => `<div class="item"><div><div class="t">${esc(v.display_name)}</div>
        <div class="muted small">${fmtDate(v.visit_date)} ・ ${esc(v.rep_name || "")}${v.memo ? " ・ " + esc(v.memo) : ""}</div></div>
        ${v.editable ? `<div class="row"><button class="btn sm" data-e="${v.id}">編集</button><button class="btn sm danger" data-x="${v.id}">削除</button></div>` : ""}</div>`).join("")}</div>` : `<div class="empty">まだ訪問の記録がありません</div>`;
      $$("[data-e]", box).forEach((b) => (b.onclick = () => {
        editing = d.items.find((v) => v.id == b.dataset.e);
        store = { code: editing.store_code, display_name: editing.display_name, company: editing.company };
        $d.value = editing.visit_date; $r.value = editing.rep_code; $m.value = editing.memo;
        $("#ttl").textContent = "訪問を編集"; $("#go").textContent = "更新する"; $("#cancel").hidden = false; renderStore(); window.scrollTo(0, 0);
      }));
      $$("[data-x]", box).forEach((b) => (b.onclick = async () => {
        if (!(await confirmBox("この訪問を削除しますか?(元に戻せません)", "削除する", true))) return;
        try { await api("/api/visits/" + b.dataset.x, { method: "DELETE" }); toast("削除しました"); if (editing && editing.id == b.dataset.x) reset(); loadRecent(); } catch (e) { if (!e.handled) toast(e.message); }
      }));
    } catch (e) { fail(box, e, loadRecent); }
  }
  function reset() {
    editing = null; store = null; $m.value = ""; $("#ttl").textContent = "訪問を入力"; $("#go").textContent = "登録する"; $("#cancel").hidden = true; renderStore();
  }
  $("#cancel").onclick = reset;
  $("#f").onsubmit = async (ev) => {
    ev.preventDefault(); const msg = $("#msg"); msg.innerHTML = "";
    if (!store) { msg.innerHTML = `<div class="alert err">店舗を選んでください</div>`; return; }
    const body = { visit_date: $d.value, store_code: store.code, rep_code: $r.value, memo: $m.value, force: false };
    const btn = $("#go"); btn.disabled = true;
    try {
      for (;;) {
        try {
          if (editing) await api("/api/visits/" + editing.id, { method: "PUT", json: body });
          else await api("/api/visits", { json: body });
          break;
        } catch (e) {
          if (e.status === 409 && !body.force) { if (await confirmBox(e.message, "登録する")) { body.force = true; continue; } btn.disabled = false; return; }
          throw e;
        }
      }
      toast(editing ? "更新しました" : "登録しました ✔"); reset(); loadRecent();
    } catch (e) { if (!e.handled) msg.innerHTML = `<div class="alert err">${esc(e.message)}</div>`; }
    btn.disabled = false;
  };
  loadRecent();
}

// ---------- 店舗一覧 ----------
const SF = { q: "", rep: "", company: "", min: "", sort: "days", order: "desc" };
async function vStores(el) {
  el.innerHTML = `<h1>店舗一覧</h1><div class="card"><input id="q" type="search" placeholder="店舗名・得意先コード・得意先名で検索" value="${esc(SF.q)}">
    <div class="row" style="margin-top:8px"><select id="rep" class="grow"><option value="">営業: すべて</option>${S.meta.reps.map((r) => `<option value="${esc(r.code)}">${esc(r.name)}</option>`).join("")}</select>
    <select id="co" class="grow"><option value="">得意先(法人): すべて</option>${S.meta.companies.map((c) => `<option>${esc(c)}</option>`).join("")}</select></div>
    <div style="margin-top:8px"><select id="min"><option value="">経過日数: すべて</option><option value="30">30日以上</option><option value="60">60日以上</option><option value="90">90日以上</option><option value="unvisited">未訪問のみ</option></select></div>
    <div class="row" style="margin-top:8px"><select id="sort" class="grow"><option value="days">並べ替え: 経過日数</option><option value="last_visit">並べ替え: 最終訪問日</option><option value="company">並べ替え: 得意先名</option></select>
    <select id="ord" style="width:auto"><option value="desc">降順</option><option value="asc">昇順</option></select></div></div><div id="cnt" class="muted small"></div><div id="list" class="list"></div>`;
  $("#rep").value = SF.rep; $("#co").value = SF.company; $("#min").value = SF.min; $("#sort").value = SF.sort; $("#ord").value = SF.order;
  let seq = 0;
  const run = async () => {
    const my = ++seq; const list = $("#list");
    SF.q = $("#q").value; SF.rep = $("#rep").value; SF.company = $("#co").value; SF.min = $("#min").value; SF.sort = $("#sort").value; SF.order = $("#ord").value;
    list.innerHTML = loading();
    try {
      const d = await api("/api/stores" + qs({ q: SF.q, rep: SF.rep, company: SF.company, sort: SF.sort, order: SF.order,
        unvisited: SF.min === "unvisited" ? 1 : "", min_days: SF.min && SF.min !== "unvisited" ? SF.min : "" }));
      if (my !== seq) return;
      $("#cnt").textContent = `${d.count}店舗(赤は${S.meta.threshold_days}日以上、または未訪問)`;
      list.innerHTML = d.items.length ? d.items.map(storeItem).join("") : `<div class="empty">条件に合う店舗がありません</div>`;
    } catch (e) { fail(list, e, run); }
  };
  let t; $("#q").oninput = () => { clearTimeout(t); t = setTimeout(run, 250); };
  ["rep", "co", "min", "sort", "ord"].forEach((id) => ($("#" + id).onchange = run));
  run();
}

async function vStoreDetail(el, code) {
  const d = await api("/api/stores/" + encodeURIComponent(code)); const s = d.store;
  el.innerHTML = `<p><a href="#/stores">← 店舗一覧</a></p><h1>${esc(s.display_name)}</h1>
    <div class="card"><div class="muted small">${esc(s.company)} ・ 得意先コード ${esc(s.code)} ・ 担当 ${esc(s.rep_name || "")}</div>
    <div style="margin:8px 0">最終訪問日: <b>${s.last_visit ? fmtDate(s.last_visit) : "未訪問"}</b> ${elapsedBadge(s)}</div>
    <a class="btn pri" href="#/visit?store=${encodeURIComponent(s.code)}">＋ この店舗の訪問を入力</a></div>
    <h2>訪問履歴(${d.visits.length}件)</h2>${d.visits.length ? `<div class="card scroll"><table><thead><tr><th>日付</th><th>営業</th><th>メモ</th></tr></thead><tbody>${d.visits.map((v) => `<tr><td>${fmtDate(v.visit_date)}</td><td>${esc(v.rep_name || v.rep_code)}</td><td>${esc(v.memo)}</td></tr>`).join("")}</tbody></table></div>` : `<div class="empty">まだ訪問の記録がありません</div>`}`;
}

// ---------- 集計 ----------
const statsTabs = (on) => `<div class="seg" style="margin-bottom:12px"><a href="#/stats/monthly" class="${on === "m" ? "on" : ""}">月別</a><a href="#/stats/rep" class="${on === "r" ? "on" : ""}">営業別</a></div>`;
const repOptions = (all) => (all ? `<option value="">全員</option>` : "") + S.meta.reps.map((r) => `<option value="${esc(r.code)}">${esc(r.name)}</option>`).join("");

function barChart(trend) {
  const series = [["stores", "訪問した店舗数", "#2563eb"], ["companies", "訪問した法人数", "#d97706"], ["visits", "訪問回数", "#059669"]];
  const W = 640, H = 230, L = 34, B = 26, T = 8, n = trend.length, gw = (W - L - 6) / n;
  const max = Math.max(1, ...trend.flatMap((t) => series.map(([k]) => t[k])));
  const nice = Math.max(1, Math.ceil(max / 4)) * 4, ph = H - B - T;
  let g = ""; for (let i = 0; i <= 4; i++) { const y = T + ph - (ph * i) / 4; g += `<line x1="${L}" x2="${W}" y1="${y}" y2="${y}" stroke="currentColor" opacity=".12"/><text x="${L - 5}" y="${y + 4}" text-anchor="end">${(nice * i) / 4}</text>`; }
  let bars = "";
  trend.forEach((t, i) => {
    const bw = Math.min(14, (gw - 6) / 3);
    series.forEach(([k, nm, c], j) => {
      const h = (ph * t[k]) / nice, x = L + i * gw + (gw - bw * 3) / 2 + j * bw;
      bars += `<rect x="${x.toFixed(1)}" y="${(T + ph - h).toFixed(1)}" width="${(bw - 1).toFixed(1)}" height="${h.toFixed(1)}" fill="${c}" rx="1.5"><title>${t.month} ${nm}: ${t[k]}</title></rect>`;
    });
    bars += `<text x="${(L + i * gw + gw / 2).toFixed(1)}" y="${H - 8}" text-anchor="middle">${Number(t.month.slice(5))}月</text>`;
  });
  return `<div class="legend">${series.map(([, nm, c]) => `<span><i style="background:${c}"></i>${nm}</span>`).join("")}</div>
    <svg class="chart" viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="直近12か月の推移グラフ">${g}${bars}</svg>`;
}

async function vMonthly(el, q) {
  const ym = q.month || S.meta.today.slice(0, 7), rep = q.rep || "";
  const go = (o) => (location.hash = "#/stats/monthly" + qs({ month: ym, rep, ...o }));
  const d = await api("/api/stats/monthly" + qs({ month: ym, rep }));
  el.innerHTML = `${statsTabs("m")}<h1>月別の件数</h1><div class="row" style="margin-bottom:10px"><div class="monthnav"><button class="btn sm" id="pv" aria-label="前月">◀</button>
    <input type="month" id="mo" value="${ym}" aria-label="月"><button class="btn sm" id="nx" aria-label="翌月">▶</button></div>
    <select id="rp" style="width:auto">${repOptions(true)}</select></div>
    <h2>${fmtMonth(ym)}${rep ? "(" + esc((S.meta.reps.find((r) => r.code === rep) || {}).name || rep) + ")" : ""}</h2>${kpiRow(d.summary)}
    <h2>法人別の内訳</h2>${d.companies.length ? `<div class="card scroll"><table><thead><tr><th>法人(得意先名)</th><th class="n">訪問店舗数</th><th class="n">訪問回数</th><th class="n">担当店舗数</th></tr></thead><tbody>${d.companies.map((c) => `<tr><td>${esc(c.company)}</td><td class="n">${c.visited_stores}</td><td class="n">${c.visits}</td><td class="n">${c.assigned_stores}</td></tr>`).join("")}</tbody></table></div>` : `<div class="empty">データがありません</div>`}
    <h2>直近12か月の推移</h2><div class="card">${barChart(d.trend)}</div>
    <div class="card scroll"><table><thead><tr><th>月</th><th class="n">訪問した店舗数</th><th class="n">訪問した法人数</th><th class="n">訪問回数</th></tr></thead><tbody>${d.trend.slice().reverse().map((t) => `<tr><td>${fmtMonth(t.month)}</td><td class="n">${t.stores}</td><td class="n">${t.companies}</td><td class="n">${t.visits}</td></tr>`).join("")}</tbody></table></div>`;
  $("#rp").value = rep;
  $("#pv").onclick = () => go({ month: addMonths(ym, -1) }); $("#nx").onclick = () => go({ month: addMonths(ym, 1) });
  $("#mo").onchange = (e) => e.target.value && go({ month: e.target.value }); $("#rp").onchange = (e) => go({ rep: e.target.value });
}

function periodQuery(q) {
  if (q.start && q.end) return { start: q.start, end: q.end };
  return { month: q.month || S.meta.today.slice(0, 7) };
}
async function vByRep(el, q) {
  const per = periodQuery(q), isRange = !!per.start;
  const go = (o) => (location.hash = "#/stats/rep" + qs(o));
  const d = await api("/api/stats/by-rep" + qs(per));
  const label = isRange ? `${fmtDate(per.start)} 〜 ${fmtDate(per.end)}` : fmtMonth(per.month);
  const row = (r, link) => `<tr ${link ? `class="click" data-rep="${esc(r.rep_code)}"` : ""}><td>${link ? `<a href="#/stats/rep/${encodeURIComponent(r.rep_code)}${qs(per)}">${esc(r.rep_name)}</a>` : "<b>全体</b>"}</td><td class="n">${r.visits}</td><td class="n">${r.stores}</td><td class="n">${r.assigned_stores}</td><td class="n">${pct(r.rate)}</td></tr>`;
  el.innerHTML = `${statsTabs("r")}<h1>営業別の訪問件数</h1><div class="row" style="margin-bottom:10px"><div class="seg"><button id="mM" class="${isRange ? "" : "on"}">月</button><button id="mR" class="${isRange ? "on" : ""}">期間</button></div>
    ${isRange ? `<input type="date" id="s" value="${per.start}" style="width:auto"> 〜 <input type="date" id="e" value="${per.end}" style="width:auto">` : `<div class="monthnav"><button class="btn sm" id="pv" aria-label="前月">◀</button><input type="month" id="mo" value="${per.month}"><button class="btn sm" id="nx" aria-label="翌月">▶</button></div>`}
    ${S.me.role === "admin" ? `<a class="btn sm" href="/api/stats/by-rep/csv${qs(per)}" download>CSVダウンロード</a>` : ""}</div>
    <p class="muted">${label} ・ 訪問率 = 担当店舗のうち期間内に訪問した店舗の割合</p>
    <div class="card scroll"><table><thead><tr><th>営業</th><th class="n">訪問回数</th><th class="n">訪問店舗数</th><th class="n">担当店舗数</th><th class="n">訪問率</th></tr></thead><tbody>${d.reps.map((r) => row(r, true)).join("")}${row({ visits: d.total.visits, stores: d.total.stores, assigned_stores: d.total.assigned_stores, rate: d.total.rate }, false)}</tbody></table></div>`;
  $$("tr[data-rep]").forEach((tr) => (tr.onclick = (ev) => { if (ev.target.tagName !== "A") location.hash = `#/stats/rep/${encodeURIComponent(tr.dataset.rep)}${qs(per)}`; }));
  $("#mM").onclick = () => go({ month: S.meta.today.slice(0, 7) });
  $("#mR").onclick = () => { const t = S.meta.today; go({ start: t.slice(0, 8) + "01", end: t }); };
  if (isRange) { $("#s").onchange = $("#e").onchange = () => $("#s").value && $("#e").value && go({ start: $("#s").value, end: $("#e").value }); }
  else { $("#pv").onclick = () => go({ month: addMonths(per.month, -1) }); $("#nx").onclick = () => go({ month: addMonths(per.month, 1) }); $("#mo").onchange = (e) => e.target.value && go({ month: e.target.value }); }
}

async function vRepDetail(el, code, q) {
  const per = periodQuery(q); const d = await api(`/api/stats/rep/${encodeURIComponent(code)}` + qs(per));
  const rep = S.meta.reps.find((r) => r.code === code); const label = per.start ? `${fmtDate(per.start)} 〜 ${fmtDate(per.end)}` : fmtMonth(per.month);
  el.innerHTML = `<p><a href="#/stats/rep${qs(per)}">← 営業別</a></p><h1>${esc(rep ? rep.name : code)}</h1><p class="muted">${label}</p>${kpiRow(d.summary)}
    <h2>法人別の件数</h2><div class="card scroll"><table><thead><tr><th>法人</th><th class="n">訪問店舗数</th><th class="n">訪問回数</th><th class="n">担当店舗数</th></tr></thead><tbody>${d.companies.filter((c) => c.visits > 0).map((c) => `<tr><td>${esc(c.company)}</td><td class="n">${c.visited_stores}</td><td class="n">${c.visits}</td><td class="n">${c.assigned_stores}</td></tr>`).join("") || `<tr><td colspan="4" class="empty">この期間の訪問はありません</td></tr>`}</tbody></table></div>
    <h2>訪問履歴</h2><div class="card scroll"><table><thead><tr><th>日付</th><th>店舗</th><th>メモ</th></tr></thead><tbody>${d.visits.map((v) => `<tr><td>${fmtDate(v.visit_date)}</td><td><a href="#/store/${encodeURIComponent(v.store_code)}">${esc(v.store_name || v.company)}</a><div class="muted small">${esc(v.company)}</div></td><td>${esc(v.memo)}</td></tr>`).join("") || `<tr><td colspan="3" class="empty">この期間の訪問はありません</td></tr>`}</tbody></table></div>`;
}

// ---------- 管理 ----------
async function vAdmin(el) {
  if (S.me.role !== "admin") { el.innerHTML = `<div class="alert err">管理者のみ利用できます</div>`; return; }
  el.innerHTML = `<h1>管理</h1>
   <div class="card"><h2 style="margin-top:0">担当店舗マスタの取り込み</h2><p class="muted small">xlsx(列: 営業コード・営業担当者・得意先コード・得意先名・店舗名)。再取り込みしても訪問履歴は残ります。重複や空欄はレポートに表示し、自動では削除・統合しません。</p>
   <input type="file" id="file" accept=".xlsx"><div style="margin-top:8px"><button class="btn pri" id="imp">取り込む</button></div><div id="impres"></div></div>
   <div class="card"><h2 style="margin-top:0">設定</h2><label class="f" for="th">経過日数の警告しきい値(日)</label><div class="row"><input id="th" type="number" min="1" max="3650" style="width:120px" value="${S.meta.threshold_days}"><button class="btn" id="thsave">保存</button></div></div>
   <div class="card"><h2 style="margin-top:0">ユーザー</h2><div id="users">${loading()}</div></div>
   <div class="card"><h2 style="margin-top:0">取引先名の候補一覧(表記ゆれの確認用)</h2><div id="cands">${loading()}</div></div>
   <div class="card"><h2 style="margin-top:0">取り込み履歴</h2><div id="logs">${loading()}</div></div>`;
  $("#thsave").onclick = async () => {
    try { const r = await api("/api/admin/settings", { method: "PUT", json: { threshold_days: Number($("#th").value) } }); S.meta.threshold_days = r.threshold_days; toast("保存しました"); } catch (e) { if (!e.handled) toast(e.message); }
  };
  const reportHtml = (r) => `<div class="alert ${r.errors.length || r.duplicates.length ? "warn" : "ok"}">行数 ${r.total_rows} / 新規店舗 ${r.new_stores} / 更新 ${r.updated_stores} / 変更なし ${r.unchanged_stores} / 無効化 ${r.deactivated_stores} / 店舗名空欄 ${r.blank_store_names} / 新規営業 ${r.new_reps}</div>
    ${r.padded_codes ? `<div class="alert warn">先頭を0埋めした得意先コード: ${r.padded_codes}件</div>` : ""}
    ${r.duplicates && r.duplicates.length ? `<h2>重複する得意先コード(${r.duplicates.length}件・最初の行のみ採用)</h2><div class="scroll"><table><thead><tr><th>コード</th><th>採用(行)</th><th>未採用(行)</th></tr></thead><tbody>${r.duplicates.map((x) => `<tr><td>${esc(x.code)}</td><td>${esc(x.kept)}(${x.kept_row})</td><td>${esc(x.skipped)}(${x.skipped_row})</td></tr>`).join("")}</tbody></table></div>` : ""}
    ${r.errors && r.errors.length ? `<h2>取り込めなかった行</h2><ul>${r.errors.map((x) => `<li>${x.row}行目: ${esc(x.message)}</li>`).join("")}</ul>` : ""}
    ${r.warnings && r.warnings.length ? `<h2>警告</h2><ul>${r.warnings.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}`;
  $("#imp").onclick = async () => {
    const f = $("#file").files[0]; if (!f) return toast("ファイルを選んでください");
    const fd = new FormData(); fd.append("file", f); const b = $("#imp"); b.disabled = true; $("#impres").innerHTML = loading();
    try {
      const r = await api("/api/admin/import", { method: "POST", body: fd });
      $("#impres").innerHTML = reportHtml(r) + (r.new_users.length ? `<h2>新規ユーザーの一時パスワード(この画面でのみ表示)</h2><div class="alert warn">本人に安全な方法で伝えてください。初回ログイン時に変更が必要です。</div><div class="scroll"><table><thead><tr><th>ID</th><th>氏名</th><th>一時パスワード</th></tr></thead><tbody>${r.new_users.map((u) => `<tr><td>${esc(u.id)}</td><td>${esc(u.name)}</td><td><code>${esc(u.temp_password)}</code></td></tr>`).join("")}</tbody></table></div>` : "");
      S.meta = await api("/api/meta"); loadCands(); loadLogs(); loadUsers();
    } catch (e) { if (!e.handled) $("#impres").innerHTML = `<div class="alert err">${esc(e.message)}</div>`; }
    b.disabled = false;
  };
  async function loadUsers() {
    const box = $("#users");
    try {
      const d = await api("/api/admin/users");
      box.innerHTML = `<div class="scroll"><table><thead><tr><th>ID</th><th>氏名</th><th>役割</th><th>状態</th><th></th></tr></thead><tbody>${d.items.map((u) => `<tr><td>${esc(u.id)}</td><td>${esc(u.rep_name || "(管理者)")}</td>
        <td><select data-role="${esc(u.id)}" style="min-height:36px"><option value="sales" ${u.role === "sales" ? "selected" : ""}>営業</option><option value="admin" ${u.role === "admin" ? "selected" : ""}>管理者</option></select></td>
        <td>${u.active ? "有効" : "無効"}${u.must_change ? " <span class='badge b-amber'>初回PW未変更</span>" : ""}</td>
        <td class="row"><button class="btn sm" data-rs="${esc(u.id)}">PW再発行</button><button class="btn sm" data-ac="${esc(u.id)}" data-v="${u.active ? 0 : 1}">${u.active ? "無効化" : "有効化"}</button></td></tr>`).join("")}</tbody></table></div>`;
      $$("[data-role]", box).forEach((s) => (s.onchange = async () => { try { await api("/api/admin/users/" + encodeURIComponent(s.dataset.role), { method: "PATCH", json: { role: s.value } }); toast("役割を変更しました"); } catch (e) { if (!e.handled) toast(e.message); loadUsers(); } }));
      $$("[data-rs]", box).forEach((b) => (b.onclick = async () => { if (!(await confirmBox(`${b.dataset.rs} のパスワードを再発行しますか?`, "再発行"))) return; try { const r = await api(`/api/admin/users/${encodeURIComponent(b.dataset.rs)}/reset-password`, { method: "POST" }); infoBox(`<p><b>${esc(r.id)}</b> の一時パスワード:</p><pre class="cred">${esc(r.temp_password)}</pre><p class="muted small">この画面を閉じると再表示できません。</p>`); } catch (e) { if (!e.handled) toast(e.message); } }));
      $$("[data-ac]", box).forEach((b) => (b.onclick = async () => { try { await api("/api/admin/users/" + encodeURIComponent(b.dataset.ac), { method: "PATCH", json: { active: b.dataset.v === "1" } }); loadUsers(); } catch (e) { if (!e.handled) toast(e.message); } }));
    } catch (e) { fail(box, e, loadUsers); }
  }
  async function loadCands() {
    const box = $("#cands");
    try {
      const d = await api("/api/admin/name-candidates");
      box.innerHTML = d.groups.length ? d.groups.map((g) => `<div style="margin-bottom:10px"><div class="muted small">${esc(g.reason)}</div>${g.names.map((n) => `<div>${esc(n.name)} <span class="muted small">(${n.stores}店舗)</span></div>`).join("")}</div>`).join("") + `<p class="muted small">自動では統合していません。必要ならマスタ側の表記を修正して再取り込みしてください。</p>` : `<div class="empty">表記ゆれの候補はありません</div>`;
    } catch (e) { fail(box, e, loadCands); }
  }
  async function loadLogs() {
    const box = $("#logs");
    try {
      const d = await api("/api/admin/import-log");
      box.innerHTML = d.items.length ? `<div class="scroll"><table><thead><tr><th>日時</th><th>実行者</th><th>ファイル</th><th>結果</th></tr></thead><tbody>${d.items.map((l) => `<tr><td>${esc(l.imported_at.replace("T", " "))}</td><td>${esc(l.imported_by)}</td><td>${esc(l.filename)}</td><td class="small">新規${l.report.new_stores}/更新${l.report.updated_stores}/無効化${l.report.deactivated_stores}/重複${l.report.duplicates.length}</td></tr>`).join("")}</tbody></table></div>` : `<div class="empty">まだ取り込みがありません</div>`;
    } catch (e) { fail(box, e, loadLogs); }
  }
  loadUsers(); loadCands(); loadLogs();
}

// ---------- 起動 ----------
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
boot();
