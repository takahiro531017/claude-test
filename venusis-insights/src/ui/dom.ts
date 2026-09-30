export const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

export function $<T extends HTMLElement = HTMLElement>(sel: string, root: ParentNode = document): T {
  const el = root.querySelector<T>(sel);
  if (!el) throw new Error(`要素が見つかりません: ${sel}`);
  return el;
}

let toastTimer = 0;
export function toast(msg: string) {
  const el = $('#toast');
  el.textContent = msg;
  el.hidden = false;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => (el.hidden = true), 3500);
}

export function miniTable(headers: string[], rows: (string | number)[][]): string {
  return `<table class="mini-table"><thead><tr>${headers.map((h) => `<th scope="col">${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows
    .map((r) => `<tr>${r.map((c, i) => (i === 0 ? `<th scope="row">${esc(String(c))}</th>` : `<td>${esc(String(c))}</td>`)).join('')}</tr>`)
    .join('')}</tbody></table>`;
}

export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
