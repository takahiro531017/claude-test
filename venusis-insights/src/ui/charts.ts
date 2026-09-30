import {
  BarController, BarElement, CategoryScale, Chart, LineController, LineElement, LinearScale, PointElement, Tooltip,
  type ChartConfiguration, type Plugin,
} from 'chart.js';
import { byType, monthly } from '../analytics/groupings';
import { fmtCompact, fmtInt, fmtPct } from '../analytics/metrics';
import { POST_TYPE_LABEL, type Post } from '../data/types';
import { $, cssVar, miniTable } from './dom';

Chart.register(BarController, BarElement, CategoryScale, LineController, LineElement, LinearScale, PointElement, Tooltip);

/** 値をグラフ上に直接書く（件数が多いときは省略。数値は表・ツールチップで確認できる） */
const valueLabels: Plugin = {
  id: 'valueLabels',
  afterDatasetsDraw(chart, _a, opts: { format?: (v: number) => string; maxPoints?: number }) {
    const { ctx } = chart;
    const ds = chart.data.datasets[0];
    if (!opts.format || chart.data.labels!.length > (opts.maxPoints ?? 9)) return;
    const meta = chart.getDatasetMeta(0);
    ctx.save();
    ctx.fillStyle = cssVar('--ink');
    ctx.font = `500 12px ${getComputedStyle(document.body).fontFamily}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';
    meta.data.forEach((el, i) => {
      const v = ds.data[i];
      if (typeof v !== 'number') return;
      ctx.fillText(opts.format!(v), el.x, el.y - 6);
    });
    ctx.restore();
  },
};
Chart.register(valueLabels);

const charts = new Map<string, Chart>();

function mount(id: string, cfg: ChartConfiguration) {
  charts.get(id)?.destroy();
  charts.set(id, new Chart($<HTMLCanvasElement>('#' + id), cfg));
}

function baseOptions(yFormat: (v: number) => string, labelFmt: (v: number) => string, extraTip: (i: number) => string[], tipName: string, tipFmt: (v: number) => string, headroom: number) {
  const ink = cssVar('--ink');
  const muted = cssVar('--muted');
  const grid = cssVar('--grid');
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: false as const,
    layout: { padding: { top: 18 } },
    interaction: { mode: 'index' as const, intersect: false },
    scales: {
      x: { grid: { display: false }, ticks: { color: ink, font: { size: 12 }, maxRotation: 0, autoSkip: true }, border: { color: grid } },
      y: {
        beginAtZero: true,
        grace: headroom + '%',
        grid: { color: grid },
        border: { display: false },
        ticks: { color: muted, font: { size: 11 }, maxTicksLimit: 5, callback: (v: string | number) => yFormat(Number(v)) },
      },
    },
    plugins: {
      legend: { display: false },
      valueLabels: { format: labelFmt },
      tooltip: {
        displayColors: false,
        padding: 10,
        titleFont: { size: 13 },
        bodyFont: { size: 13 },
        backgroundColor: ink,
        titleColor: cssVar('--bg'),
        bodyColor: cssVar('--bg'),
        callbacks: {
          label: (c: { parsed: { y: number | null } }) => `${tipName}: ${c.parsed.y === null ? 'データなし' : tipFmt(c.parsed.y)}`,
          afterLabel: (c: { dataIndex: number }) => extraTip(c.dataIndex),
        },
      },
    },
  };
}

/** monthlyPosts: 月別グラフ用（全期間）、typePosts: 投稿タイプ別グラフ用（選択期間） */
export function renderCharts(monthlyPosts: Post[], typePosts: Post[]) {
  const months = monthly(monthlyPosts);
  const types = byType(typePosts);

  mount('c-month-reach', {
    type: 'bar',
    data: {
      labels: months.map((m) => m.label),
      datasets: [{ data: months.map((m) => m.totalReach), backgroundColor: cssVar('--c-reel'), borderRadius: { topLeft: 4, topRight: 4 }, maxBarThickness: 44 }],
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    options: baseOptions(fmtCompact, fmtCompact, (i) => [`投稿数: ${months[i].count}本`], '合計リーチ', (v) => `${fmtInt(v)}人`, 8) as any,
  });

  mount('c-month-er', {
    type: 'line',
    data: {
      labels: months.map((m) => m.label),
      datasets: [{
        data: months.map((m) => (m.er === null ? null : m.er * 100)),
        borderColor: cssVar('--c-line'), backgroundColor: cssVar('--surface'), borderWidth: 2, tension: 0,
        pointRadius: 5, pointHoverRadius: 7, pointBorderWidth: 2, pointBackgroundColor: cssVar('--surface'), spanGaps: false,
      }],
    },
    options: baseOptions((v) => `${v}%`, (v) => `${v.toFixed(1)}%`, (i) => [`投稿数: ${months[i].count}本`], '平均エンゲージメント率', (v) => `${v.toFixed(2)}%`, 15) as any,
  });

  const colors = [cssVar('--c-reel'), cssVar('--c-feed'), cssVar('--c-story')];
  const tLabels = types.map((t) => `${POST_TYPE_LABEL[t.type]}（${t.count}本）`);
  const typeBar = (id: string, data: (number | null)[], yFmt: (v: number) => string, name: string, tipFmt: (v: number) => string) =>
    mount(id, {
      type: 'bar',
      data: { labels: tLabels, datasets: [{ data, backgroundColor: colors, borderRadius: { topLeft: 4, topRight: 4 }, maxBarThickness: 56 }] },
      options: baseOptions(yFmt, yFmt, (i) => (types[i].count === 0 ? ['この期間は投稿なし'] : []), name, tipFmt, 12) as any,
    });
  typeBar('c-type-reach', types.map((t) => t.avgReach), fmtCompact, '平均リーチ', (v) => `${fmtInt(v)}人`);
  typeBar('c-type-er', types.map((t) => (t.er === null ? null : t.er * 100)), (v) => `${Number(v.toFixed(1))}%`, '平均エンゲージメント率', (v) => `${v.toFixed(2)}%`);

  $('#t-month-reach').innerHTML = miniTable(['月', '合計リーチ', '投稿数'], months.map((m) => [m.label, fmtInt(m.totalReach), `${m.count}本`]));
  $('#t-month-er').innerHTML = miniTable(['月', '平均エンゲージメント率', '投稿数'], months.map((m) => [m.label, fmtPct(m.er, 2), `${m.count}本`]));
  $('#t-type').innerHTML = miniTable(['タイプ', '投稿数', '平均リーチ', 'エンゲージメント率', '保存率'], types.map((t) => [POST_TYPE_LABEL[t.type], `${t.count}本`, t.avgReach === null ? '—' : fmtInt(t.avgReach), fmtPct(t.er, 2), fmtPct(t.saveRate, 2)]));
}
