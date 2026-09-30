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

/** ブラウザ標準の confirm() が使えない環境（埋め込み表示など）でも動く、ページ内の確認ダイアログ */
export function confirmDialog(message: string, okLabel: string): Promise<boolean> {
  return new Promise((resolve) => {
    const back = document.createElement('div');
    back.className = 'modal-back';
    back.innerHTML = `<div class="modal" role="alertdialog" aria-modal="true" aria-label="確認"><p>${esc(message)}</p><div class="btn-row"><button type="button" class="btn" data-r="0">キャンセル</button><button type="button" class="btn btn-primary" data-r="1">${esc(okLabel)}</button></div></div>`;
    const done = (r: boolean) => {
      back.remove();
      document.removeEventListener('keydown', onKey);
      resolve(r);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && done(false);
    document.addEventListener('keydown', onKey);
    back.addEventListener('click', (e) => {
      const t = (e.target as HTMLElement).closest<HTMLElement>('[data-r]');
      if (t) done(t.dataset.r === '1');
      else if (e.target === back) done(false);
    });
    document.body.appendChild(back);
    back.querySelector<HTMLElement>('[data-r="0"]')!.focus();
  });
}
