import { TIME_BANDS } from '../config/columnMap';
import { heatmap, WEEKDAYS } from '../analytics/groupings';
import { fmtCompact, fmtInt } from '../analytics/metrics';
import type { Post } from '../data/types';
import { esc } from './dom';

const STEPS = 5;
let hideCurrent: () => void = () => {};
document.addEventListener('click', () => hideCurrent());
document.addEventListener('keydown', (e) => e.key === 'Escape' && hideCurrent());

export function renderHeatmap(el: HTMLElement, posts: Post[]) {
  const grid = heatmap(posts);
  const counted = grid.flat().filter((c) => c.count > 0);
  if (counted.length === 0) {
    el.innerHTML = '<p class="note">この期間には、時刻つきのフィード／リール投稿がありません。</p>';
    return;
  }
  const max = Math.max(...counted.map((c) => c.avgReach!));
  const level = (v: number) => Math.min(STEPS, Math.max(1, Math.ceil((v / max) * STEPS)));

  const head = TIME_BANDS.map((b) => {
    const [name, range] = b.label.split(' ');
    return `<th scope="col"><span class="band-name">${esc(name)}</span>${esc(range.replace('時', ''))}</th>`;
  }).join('');
  const body = grid
    .map((row, d) => {
      const cells = row
        .map((c) => {
          const name = `${WEEKDAYS[d]}曜 ${TIME_BANDS[c.band].label}`;
          if (c.count === 0) return `<td><button type="button" class="heat-cell lv0" data-tip="${esc(name)}：投稿なし" aria-label="${esc(name)}：投稿なし">—</button></td>`;
          const few = c.count < 2;
          const tip = `${name}\n平均リーチ ${fmtInt(c.avgReach!)}（${c.count}件）${few ? '\n※1件だけのため参考値' : ''}`;
          return `<td><button type="button" class="heat-cell lv${level(c.avgReach!)}${few ? ' few' : ''}" data-tip="${esc(tip)}" aria-label="${esc(tip.replace(/\n/g, '、'))}">${fmtCompact(c.avgReach!)}</button></td>`;
        })
        .join('');
      return `<tr><th scope="row">${WEEKDAYS[d]}</th>${cells}</tr>`;
    })
    .join('');

  el.innerHTML = `<div class="heat-wrap">
    <table class="heat"><thead><tr><td></td>${head}</tr></thead><tbody>${body}</tbody></table>
    <div class="heat-tip" hidden></div></div>
    <div class="heat-legend"><span>少ない</span><span class="sw">${[1, 2, 3, 4, 5].map((l) => `<i class="lv${l}"></i>`).join('')}</span><span>多い</span><span>／ 点線の枠は1件だけの参考値、「—」は投稿なし</span></div>
    <p class="note">数字は、その枠に投稿したときの平均リーチ（人）です。枠をタップ（クリック）すると詳細が出ます。</p>`;

  const wrap = el.querySelector<HTMLElement>('.heat-wrap')!;
  const tip = wrap.querySelector<HTMLElement>('.heat-tip')!;
  const show = (btn: HTMLElement) => {
    tip.innerHTML = esc(btn.dataset.tip!).replace(/\n/g, '<br>');
    tip.hidden = false;
    const w = wrap.getBoundingClientRect();
    const b = btn.getBoundingClientRect();
    const tw = tip.offsetWidth;
    const left = Math.min(Math.max(0, b.left - w.left + b.width / 2 - tw / 2), w.width - tw);
    const top = b.top - w.top - tip.offsetHeight - 6;
    tip.style.left = left + 'px';
    tip.style.top = (top < 0 ? b.bottom - w.top + 6 : top) + 'px';
  };
  const hide = () => (tip.hidden = true);
  wrap.querySelectorAll<HTMLElement>('.heat-cell').forEach((btn) => {
    btn.addEventListener('mouseenter', () => show(btn));
    btn.addEventListener('mouseleave', hide);
    btn.addEventListener('focus', () => show(btn));
    btn.addEventListener('blur', hide);
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      show(btn);
    });
  });
  hideCurrent = hide;
}
