import './styles/main.css';
import { buildInsights } from './analytics/insights';
import { RANGE_OPTIONS, splitByRange, type RangeKey } from './analytics/metrics';
import { mergePosts } from './data/merge';
import { generateSample } from './data/sample';
import { getPref, loadPosts, savePosts, setPref } from './data/storage';
import type { Post } from './data/types';
import { renderCharts } from './ui/charts';
import { $, esc, toast } from './ui/dom';
import { renderHandover } from './ui/handover';
import { renderHeatmap } from './ui/heatmap';
import { mountImportPanel } from './ui/importPanel';
import { renderKpis } from './ui/kpiCards';
import { renderRanking, type SortKey } from './ui/rankingTable';

type Theme = 'auto' | 'light' | 'dark';

const state = {
  posts: [] as Post[],
  mode: getPref<'sample' | 'user'>('mode', 'sample'),
  range: getPref<RangeKey>('range', 90),
  sort: 'reach' as SortKey,
  expanded: false,
  theme: getPref<Theme>('theme', 'auto'),
};

function applyTheme() {
  const root = document.documentElement;
  if (state.theme === 'auto') root.removeAttribute('data-theme');
  else root.dataset.theme = state.theme;
  const label = { auto: '明るさ: 自動', light: '明るさ: ライト', dark: '明るさ: ダーク' }[state.theme];
  $('#theme-toggle').textContent = label;
}

function render() {
  const hasData = state.posts.length > 0;
  $('#sample-banner').hidden = state.mode !== 'sample';
  $('#empty').hidden = hasData;
  $('#report').hidden = !hasData;
  $('#range-seg').closest('.toolbar')!.toggleAttribute('hidden', !hasData);

  $('#range-seg').innerHTML = RANGE_OPTIONS.map((o) => `<button type="button" data-range="${o.key}" aria-pressed="${o.key === state.range}">${o.label}</button>`).join('');

  if (!hasData) return;
  const split = splitByRange(state.posts, state.range);
  $('#period-label').innerHTML = `集計期間: ${esc(split.label)}${split.previousLabel ? `　比較する期間: ${esc(split.previousLabel)}` : ''}`;
  $('#kpi-note').textContent = state.range === 'all' ? '全期間' : `直近${state.range}日（前の${state.range}日と比較）`;

  renderKpis($('#kpis'), split, state.range, state.posts);
  $('#insights').innerHTML = buildInsights(split.current, split.previous)
    .map((i) => `<li><span class="tag${i.kind === '注意' ? ' caution' : i.kind === '次にやること' ? ' action' : ''}">${i.kind}</span><span>${esc(i.text)}</span></li>`)
    .join('');
  // 月別の推移は全期間、投稿タイプ別は選択期間で描く
  renderCharts(state.posts, split.current);
  renderHeatmap($('#heatmap'), split.current);
  renderRanking($('#ranking'), split.current, state.sort, state.expanded, {
    sort: (k) => ((state.sort = k), render()),
    more: () => ((state.expanded = !state.expanded), render()),
  });
}

async function persist(posts: Post[], mode: 'sample' | 'user') {
  state.posts = posts;
  state.mode = mode;
  setPref('mode', mode);
  render();
  await savePosts(mode === 'sample' ? [] : posts);
}

async function init() {
  applyTheme();
  state.posts = state.mode === 'sample' ? generateSample() : await loadPosts();

  $('#range-seg').addEventListener('click', (e) => {
    const b = (e.target as HTMLElement).closest<HTMLElement>('[data-range]');
    if (!b) return;
    const r = b.dataset.range!;
    state.range = r === 'all' ? 'all' : (Number(r) as RangeKey);
    state.expanded = false;
    setPref('range', state.range);
    render();
  });
  $('#theme-toggle').addEventListener('click', () => {
    state.theme = ({ auto: 'light', light: 'dark', dark: 'auto' } as const)[state.theme];
    setPref('theme', state.theme);
    applyTheme();
    render();
  });
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => state.theme === 'auto' && render());
  $('#empty-sample').addEventListener('click', () => void persist(generateSample(), 'sample'));

  mountImportPanel($('#import-panel'), {
    getPosts: () => state.posts,
    isSample: () => state.mode === 'sample',
    onImported(incoming) {
      // サンプル表示中は、サンプルを捨てて実データだけにする
      const base = state.mode === 'sample' ? [] : state.posts;
      const { posts, added, updated } = mergePosts(base, incoming);
      void persist(posts, 'user');
      toast(`${added + updated}件を反映しました`);
      return { added, updated };
    },
    onClear: () => void persist([], 'user'),
    onSample: () => void persist(generateSample(), 'sample'),
  });
  renderHandover($('#handover-panel'));
  render();
}

void init();
