import { TIME_BANDS } from '../config/columnMap';
import type { Post, PostType } from '../data/types';
import { erOf, mean, parseLocal, saveRateOf } from './metrics';

export interface MonthRow {
  month: string; // YYYY-MM
  label: string; // 「9月」または「2026年1月」
  count: number;
  totalReach: number;
  er: number | null;
}

const num = <T>(xs: (T | null)[]) => xs.filter((v): v is T => v !== null);

/** 月別の集計。投稿が無い月も0/なしで埋めて、グラフが飛ばないようにする */
export function monthly(posts: Post[]): MonthRow[] {
  if (posts.length === 0) return [];
  const byMonth = new Map<string, Post[]>();
  for (const p of posts) {
    const k = p.publishedAt.slice(0, 7);
    (byMonth.get(k) ?? byMonth.set(k, []).get(k)!).push(p);
  }
  const keys = [...byMonth.keys()].sort();
  const [fy, fm] = keys[0].split('-').map(Number);
  const [ly, lm] = keys[keys.length - 1].split('-').map(Number);
  const rows: MonthRow[] = [];
  let y = fy;
  let m = fm;
  const multiYear = fy !== ly;
  while (y < ly || (y === ly && m <= lm)) {
    const key = `${y}-${String(m).padStart(2, '0')}`;
    const ps = byMonth.get(key) ?? [];
    rows.push({
      month: key,
      label: multiYear && (m === 1 || rows.length === 0) ? `${y}年${m}月` : `${m}月`,
      count: ps.length,
      totalReach: ps.reduce((a, p) => a + p.reach, 0),
      er: mean(num(ps.map(erOf))),
    });
    m++;
    if (m > 12) {
      m = 1;
      y++;
    }
  }
  return rows;
}

export interface TypeRow {
  type: PostType;
  count: number;
  avgReach: number | null;
  er: number | null;
  saveRate: number | null;
}

export function byType(posts: Post[]): TypeRow[] {
  return (['reel', 'feed', 'story'] as PostType[]).map((type) => {
    const ps = posts.filter((p) => p.type === type);
    return {
      type,
      count: ps.length,
      avgReach: mean(ps.map((p) => p.reach)),
      er: mean(num(ps.map(erOf))),
      saveRate: mean(num(ps.map(saveRateOf))),
    };
  });
}

/** 月曜始まりの曜日（表示順）。getDay() は 0=日 */
export const WEEKDAYS = ['月', '火', '水', '木', '金', '土', '日'];
export const weekdayIndex = (d: Date) => (d.getDay() + 6) % 7;
export const bandIndex = (hour: number) => TIME_BANDS.findIndex((b) => hour >= b.from && hour <= b.to);

export interface HeatCell {
  day: number; // 0=月
  band: number;
  count: number;
  avgReach: number | null;
}

/** 曜日×時間帯の平均リーチ。ストーリーズ（24時間で消える）と、時刻が不明な投稿は除く */
export function heatmap(posts: Post[]): HeatCell[][] {
  const grid: number[][][] = WEEKDAYS.map(() => TIME_BANDS.map(() => [] as number[]));
  for (const p of posts) {
    if (p.type === 'story' || !p.timeKnown) continue;
    const d = parseLocal(p.publishedAt);
    const b = bandIndex(d.getHours());
    if (b >= 0) grid[weekdayIndex(d)][b].push(p.reach);
  }
  return grid.map((row, day) => row.map((xs, band) => ({ day, band, count: xs.length, avgReach: mean(xs) })));
}
