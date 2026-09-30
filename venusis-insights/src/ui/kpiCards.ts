import { METRIC_HELP } from '../config/labels';
import { deltaCount, deltaPercent, deltaPoints, fmtInt, fmtPct, summarize, type Delta, type PeriodSplit, type RangeKey } from '../analytics/metrics';
import type { Post } from '../data/types';
import { esc } from './dom';

function card(label: string, value: string, unit: string, delta: Delta | null, helpKey: string, compareLabel: string): string {
  const help = METRIC_HELP.find((h) => h.key === helpKey)!;
  const d = delta
    ? `<div class="delta ${delta.dir}">${esc(delta.text)}</div><div class="delta-sub">${esc(compareLabel)}</div>`
    : `<div class="delta na">全期間は比較しません</div><div class="delta-sub">&nbsp;</div>`;
  return `<div class="kpi"><div class="kpi-label">${esc(label)}</div>
    <div class="kpi-value">${esc(value)}${unit ? `<small>${esc(unit)}</small>` : ''}</div>
    ${d}
    <details><summary>この数字の意味</summary><p>${esc(help.body)}</p></details></div>`;
}

export function renderKpis(el: HTMLElement, split: PeriodSplit, range: RangeKey, posts: Post[]) {
  const cur = summarize(split.current);
  const prev = split.previous ? summarize(split.previous) : null;
  const compare = range === 'all' ? '' : `前の${range}日と比べて`;
  const noPrev = prev !== null && prev.count === 0;
  const d = (f: () => Delta): Delta | null => (prev === null ? null : noPrev ? { dir: 'na', text: '比較できるデータなし' } : f());
  el.innerHTML = [
    card('投稿数', fmtInt(cur.count), '本', d(() => deltaCount(cur.count, prev!.count)), 'posts', compare),
    card('合計リーチ', fmtInt(cur.totalReach), '人', d(() => deltaPercent(cur.totalReach, prev!.totalReach)), 'reach', compare),
    card('エンゲージメント率', fmtPct(cur.er), '', d(() => deltaPoints(cur.er, prev!.er)), 'er', compare),
    card('保存率', fmtPct(cur.saveRate, 2), '', d(() => deltaPoints(cur.saveRate, prev!.saveRate)), 'save', compare),
  ].join('');
  void posts;
}
