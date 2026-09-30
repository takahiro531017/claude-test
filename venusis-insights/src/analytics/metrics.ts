import type { Post } from '../data/types';

export type RangeKey = 30 | 90 | 180 | 'all';
export const RANGE_OPTIONS: { key: RangeKey; label: string }[] = [
  { key: 30, label: '直近30日' },
  { key: 90, label: '90日' },
  { key: 180, label: '180日' },
  { key: 'all', label: '全期間' },
];

const DAY = 86400000;

export const parseLocal = (iso: string): Date => {
  const [d, t = '00:00'] = iso.split('T');
  const [y, m, dd] = d.split('-').map(Number);
  const [h, mi] = t.split(':').map(Number);
  return new Date(y, m - 1, dd, h, mi);
};

const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());

export interface PeriodSplit {
  current: Post[];
  previous: Post[] | null;
  /** 表示用の期間（YYYY/MM/DD） */
  label: string;
  previousLabel: string | null;
}

const fmt = (d: Date) => `${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}`;

/**
 * 期間で絞り込む。基準日は「データ内でいちばん新しい投稿の日」。
 * （CSVを書き出した日より後に投稿が無くても、空っぽにならないようにするため）
 * 前の期間は「同じ日数だけ前」。全期間のときは比較なし。
 */
export function splitByRange(posts: Post[], range: RangeKey): PeriodSplit {
  if (posts.length === 0) return { current: [], previous: range === 'all' ? null : [], label: '', previousLabel: null };
  const times = posts.map((p) => parseLocal(p.publishedAt).getTime());
  const endDay = startOfDay(new Date(Math.max(...times)));
  const endExclusive = endDay.getTime() + DAY;
  if (range === 'all') {
    const first = startOfDay(new Date(Math.min(...times)));
    return { current: posts, previous: null, label: `${fmt(first)}〜${fmt(endDay)}`, previousLabel: null };
  }
  const curStart = endExclusive - range * DAY;
  const prevStart = curStart - range * DAY;
  const inRange = (t: number, a: number, b: number) => t >= a && t < b;
  return {
    current: posts.filter((_, i) => inRange(times[i], curStart, endExclusive)),
    previous: posts.filter((_, i) => inRange(times[i], prevStart, curStart)),
    label: `${fmt(new Date(curStart))}〜${fmt(endDay)}`,
    previousLabel: `${fmt(new Date(prevStart))}〜${fmt(new Date(curStart - DAY))}`,
  };
}

export const engagement = (p: Post) => p.likes + p.comments + p.shares + p.saves;
/** reach が 0 の投稿は率を計算できない */
export const erOf = (p: Post): number | null => (p.reach > 0 ? engagement(p) / p.reach : null);
export const saveRateOf = (p: Post): number | null => (p.reach > 0 ? p.saves / p.reach : null);

export const mean = (xs: number[]): number | null => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
const meanOf = (posts: Post[], f: (p: Post) => number | null) => mean(posts.map(f).filter((v): v is number => v !== null));

export interface Summary {
  count: number;
  totalReach: number;
  /** 投稿ごとのエンゲージメント率の平均 */
  er: number | null;
  saveRate: number | null;
}

export function summarize(posts: Post[]): Summary {
  return {
    count: posts.length,
    totalReach: posts.reduce((a, p) => a + p.reach, 0),
    er: meanOf(posts, erOf),
    saveRate: meanOf(posts, saveRateOf),
  };
}

export interface Delta {
  dir: 'up' | 'down' | 'flat' | 'na';
  /** 例: "▲ +12.3%" / "▼ −4.1%" / "― 変化なし" / "比較できるデータなし" */
  text: string;
}

const MINUS = '−';

/** 件数・リーチなど: 増減の割合（%） */
export function deltaPercent(cur: number, prev: number | null): Delta {
  if (prev === null || prev === 0) return { dir: 'na', text: '比較できるデータなし' };
  const pct = ((cur - prev) / prev) * 100;
  if (Math.abs(pct) < 0.05) return { dir: 'flat', text: '― 変化なし' };
  return pct > 0 ? { dir: 'up', text: `▲ +${pct.toFixed(1)}%` } : { dir: 'down', text: `▼ ${MINUS}${Math.abs(pct).toFixed(1)}%` };
}

/** 率: 差をポイント（pt）で表す */
export function deltaPoints(cur: number | null, prev: number | null): Delta {
  if (cur === null || prev === null) return { dir: 'na', text: '比較できるデータなし' };
  const pt = (cur - prev) * 100;
  if (Math.abs(pt) < 0.005) return { dir: 'flat', text: '― 変化なし' };
  return pt > 0 ? { dir: 'up', text: `▲ +${pt.toFixed(2)}pt` } : { dir: 'down', text: `▼ ${MINUS}${Math.abs(pt).toFixed(2)}pt` };
}

export function deltaCount(cur: number, prev: number | null): Delta {
  if (prev === null) return { dir: 'na', text: '比較できるデータなし' };
  const d = cur - prev;
  if (d === 0) return { dir: 'flat', text: '― 変化なし' };
  return d > 0 ? { dir: 'up', text: `▲ +${d}本` } : { dir: 'down', text: `▼ ${MINUS}${Math.abs(d)}本` };
}

export const fmtInt = (n: number) => Math.round(n).toLocaleString('ja-JP');
export const fmtPct = (r: number | null, digits = 1) => (r === null ? '—' : `${(r * 100).toFixed(digits)}%`);
export const fmtCompact = (n: number) => (n >= 10000 ? `${(n / 10000).toFixed(n >= 100000 ? 0 : 1)}万` : fmtInt(n));
