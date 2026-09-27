const Api = {
  async request(method, url, body) {
    const res = await fetch(url, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (res.status === 204) return null;
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      throw new Error((data && data.error) || `リクエストに失敗しました (${res.status})`);
    }
    return data;
  },
  get(url) {
    return this.request("GET", url);
  },
  post(url, body) {
    return this.request("POST", url, body);
  },
  put(url, body) {
    return this.request("PUT", url, body);
  },
  delete(url) {
    return this.request("DELETE", url);
  },
};

const NAV_ITEMS = [
  { href: "index.html", label: "ダッシュボード" },
  { href: "inbound.html", label: "入庫登録" },
  { href: "outbound.html", label: "出荷登録" },
  { href: "history.html", label: "履歴一覧" },
  { href: "products.html", label: "商品マスタ" },
  { href: "locations.html", label: "拠点マスタ" },
];

function renderNav() {
  const mount = document.getElementById("app-header");
  if (!mount) return;
  const current = location.pathname.split("/").pop() || "index.html";
  const links = NAV_ITEMS.map(
    (item) =>
      `<a href="${item.href}" class="${item.href === current ? "active" : ""}">${item.label}</a>`
  ).join("");
  mount.innerHTML = `
    <div class="brand">在庫管理システム</div>
    <nav>${links}</nav>
  `;
}

function showMessage(mountEl, text, type = "error") {
  mountEl.innerHTML = `<div class="msg ${type}">${escapeHtml(text)}</div>`;
}

function clearMessage(mountEl) {
  mountEl.innerHTML = "";
}

function escapeHtml(str) {
  return String(str ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}

function formatDateTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function nowForInput() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

document.addEventListener("DOMContentLoaded", renderNav);
