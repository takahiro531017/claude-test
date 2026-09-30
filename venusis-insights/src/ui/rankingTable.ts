import { engagement, erOf, fmtInt, fmtPct, parseLocal } from '../analytics/metrics';
import { POST_TYPE_LABEL, type Post } from '../data/types';
import { esc } from './dom';

export type SortKey = 'reach' | 'er' | 'saves';
const SORTS: { key: SortKey; label: string }[] = [
  { key: 'reach', label: 'リーチ' },
  { key: 'er', label: 'エンゲージメント率' },
  { key: 'saves', label: '保存数' },
];

const value = (p: Post, k: SortKey) => (k === 'reach' ? p.reach : k === 'saves' ? p.saves : erOf(p) ?? -1);

const fmtDate = (p: Post) => {
  const d = parseLocal(p.publishedAt);
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`;
};

export function renderRanking(el: HTMLElement, posts: Post[], key: SortKey, expanded: boolean, on: { sort: (k: SortKey) => void; more: () => void }) {
  const sorted = [...posts].sort((a, b) => value(b, key) - value(a, key));
  const shown = expanded ? sorted.slice(0, 30) : sorted.slice(0, 10);
  const rows = shown
    .map(
      (p, i) => `<tr>
      <td class="rk num" data-label="順位">${i + 1}</td>
      <td class="dt" data-label="公開日">${fmtDate(p)}</td>
      <td class="ty" data-label="タイプ"><span class="chip ${p.type}">${POST_TYPE_LABEL[p.type]}</span></td>
      <td class="cap"><span class="meta">${i + 1}位 ・ ${fmtDate(p)} ・ <span class="chip ${p.type}">${POST_TYPE_LABEL[p.type]}</span></span>${p.caption ? esc(p.caption.length > 60 ? p.caption.slice(0, 60) + '…' : p.caption) : '<span class="note">（キャプションなし）</span>'}</td>
      <td class="num" data-label="リーチ">${fmtInt(p.reach)}</td>
      <td class="num" data-label="エンゲージメント率">${fmtPct(erOf(p))}</td>
      <td class="num" data-label="保存数">${fmtInt(p.saves)}</td></tr>`,
    )
    .join('');
  void engagement;
  const th = (k: SortKey, label: string) => `<th scope="col" class="num${k === key ? ' active' : ''}"${k === key ? ' aria-sort="descending"' : ''}>${label}${k === key ? ' ▼' : ''}</th>`;
  el.innerHTML = `<div class="rank-head">
      <div class="note" style="margin:0">上位の投稿を、選んだ項目の多い順に表示します。</div>
      <div class="seg" role="group" aria-label="並べ替え">${SORTS.map((s) => `<button type="button" data-sort="${s.key}" aria-pressed="${s.key === key}">${s.label}順</button>`).join('')}</div>
    </div>
    ${
      shown.length === 0
        ? '<p class="note">この期間の投稿がありません。</p>'
        : `<table class="rank"><thead><tr><th scope="col" class="num">順位</th><th scope="col">公開日</th><th scope="col">タイプ</th><th scope="col">キャプション</th>${th('reach', 'リーチ')}${th('er', 'エンゲージメント率')}${th('saves', '保存数')}</tr></thead><tbody>${rows}</tbody></table>`
    }
    ${sorted.length > 10 ? `<div class="more"><button type="button" class="btn" id="rank-more">${expanded ? '上位10件だけ表示' : `上位30件まで表示（全${sorted.length}件）`}</button></div>` : ''}`;
  el.querySelectorAll<HTMLButtonElement>('[data-sort]').forEach((b) => b.addEventListener('click', () => on.sort(b.dataset.sort as SortKey)));
  el.querySelector('#rank-more')?.addEventListener('click', on.more);
}
