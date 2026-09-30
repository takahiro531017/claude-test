import { describe, expect, it } from 'vitest';
import { heatmap, monthly } from '../src/analytics/groupings';
import { buildInsights } from '../src/analytics/insights';
import { deltaPercent, deltaPoints, splitByRange, summarize } from '../src/analytics/metrics';
import { buildPost } from '../src/data/normalize';
import { generateSample } from '../src/data/sample';
import type { PostType } from '../src/data/types';

const mk = (at: string, type: PostType, reach: number, eng = 0) =>
  buildPost({ publishedAt: at, timeKnown: true, caption: at + type, type, reach, likes: eng, comments: 0, shares: 0, saves: 0 }, 'manual');

describe('summarize', () => {
  it('率は投稿ごとの平均、reach=0は除外', () => {
    const s = summarize([mk('2026-03-01T10:00', 'feed', 100, 10), mk('2026-03-02T10:00', 'feed', 200, 40), mk('2026-03-03T10:00', 'feed', 0, 5)]);
    expect(s.count).toBe(3);
    expect(s.totalReach).toBe(300);
    expect(s.er).toBeCloseTo((0.1 + 0.2) / 2);
  });
  it('空でも落ちない', () => {
    expect(summarize([])).toEqual({ count: 0, totalReach: 0, er: null, saveRate: null });
  });
});

describe('delta', () => {
  it('符号と矢印を文字で出す', () => {
    expect(deltaPercent(110, 100).text).toBe('▲ +10.0%');
    expect(deltaPercent(90, 100).text).toBe('▼ −10.0%');
    expect(deltaPercent(100, 100).dir).toBe('flat');
    expect(deltaPercent(100, 0).dir).toBe('na');
    expect(deltaPoints(0.05, 0.04).text).toBe('▲ +1.00pt');
    expect(deltaPoints(0.03, 0.04).text).toBe('▼ −1.00pt');
  });
});

describe('splitByRange', () => {
  const posts = [mk('2026-01-01T10:00', 'feed', 1), mk('2026-02-10T10:00', 'feed', 2), mk('2026-03-01T10:00', 'feed', 3), mk('2026-03-31T10:00', 'feed', 4)];
  it('30日: 基準は最新投稿日。前の期間は同じ日数', () => {
    const r = splitByRange(posts, 30);
    // 現在: 3/2〜3/31、前: 1/31〜3/1
    expect(r.current.map((p) => p.reach)).toEqual([4]);
    expect(r.previous!.map((p) => p.reach)).toEqual([2, 3]);
  });
  it('全期間は比較なし', () => {
    expect(splitByRange(posts, 'all').previous).toBeNull();
  });
  it('空データ', () => {
    expect(splitByRange([], 30).current).toEqual([]);
  });
});

describe('groupings', () => {
  it('月別は空の月を埋める', () => {
    const rows = monthly([mk('2026-01-05T10:00', 'feed', 10), mk('2026-03-05T10:00', 'feed', 30)]);
    expect(rows.map((r) => [r.month, r.count])).toEqual([['2026-01', 1], ['2026-02', 0], ['2026-03', 1]]);
    expect(rows[1].er).toBeNull();
  });
  it('ヒートマップはストーリーズ・時刻不明を除く', () => {
    const st = mk('2026-03-02T21:00', 'story', 999); // 月曜
    const unk = { ...mk('2026-03-02T21:00', 'feed', 888), timeKnown: false };
    const ok = mk('2026-03-02T21:30', 'reel', 100); // 月曜の夜
    const g = heatmap([st, unk, ok]);
    expect(g[0][3]).toMatchObject({ count: 1, avgReach: 100 });
  });
});

describe('insights', () => {
  it('サンプルから文章が作れる', () => {
    const s = splitByRange(generateSample(new Date(2026, 8, 30)), 90);
    const ins = buildInsights(s.current, s.previous);
    const text = ins.map((i) => i.text).join('\n');
    expect(text).toMatch(/リールの平均リーチはフィードの[\d.]+倍/);
    expect(text).toMatch(/届きやすい時間帯は.曜の/);
    expect(ins.at(-1)!.kind).toBe('次にやること');
  });
  it('空・1件でも落ちない', () => {
    expect(buildInsights([], []).length).toBe(1);
    const one = buildInsights([mk('2026-03-01T10:00', 'reel', 100, 5)], null);
    expect(one[0].kind).toBe('注意');
  });
});
