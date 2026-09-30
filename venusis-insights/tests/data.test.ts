import { describe, expect, it } from 'vitest';
import { parseCsv, toCsv } from '../src/data/csv';
import { decodeBytes } from '../src/data/decode';
import { mergePosts } from '../src/data/merge';
import { MissingColumnsError, normalizeTable, parseDateTime, parseNumber, parseType } from '../src/data/normalize';

describe('csv', () => {
  it('引用符・カンマ・改行・BOMを扱える', () => {
    const t = parseCsv('﻿a,b\r\n"x,1","line1\nline2"\r\n"he said ""hi""",3\r\n');
    expect(t).toEqual([['a', 'b'], ['x,1', 'line1\nline2'], ['he said "hi"', '3']]);
  });
  it('タブ区切りと sep= 行', () => {
    expect(parseCsv('sep=;\na;b\n1;2')).toEqual([['a', 'b'], ['1', '2']]);
    expect(parseCsv('a\tb\n1\t2')).toEqual([['a', 'b'], ['1', '2']]);
  });
  it('toCsv は parseCsv で戻せる', () => {
    const rows = [['a', 'b,c'], ['"q"', 'x\ny']];
    expect(parseCsv(toCsv(rows))).toEqual(rows);
  });
});

describe('decode', () => {
  it('UTF-8', () => {
    expect(decodeBytes(new TextEncoder().encode('リーチ').buffer as ArrayBuffer).encoding).toBe('utf-8');
  });
  it('Shift_JIS', () => {
    // 「リーチ」= 83 8A 81 5B 83 60
    const sjis = new Uint8Array([0x83, 0x8a, 0x81, 0x5b, 0x83, 0x60]);
    const r = decodeBytes(sjis.buffer);
    expect(r.encoding).toBe('shift_jis');
    expect(r.text).toBe('リーチ');
  });
});

describe('parse helpers', () => {
  it('日付の各形式', () => {
    expect(parseDateTime('2026/03/05 18:30')).toEqual({ date: '2026-03-05', time: '18:30' });
    expect(parseDateTime('2026-3-5 7:05:59')).toEqual({ date: '2026-03-05', time: '07:05' });
    expect(parseDateTime('2026年3月5日 18:30')).toEqual({ date: '2026-03-05', time: '18:30' });
    expect(parseDateTime('03/05/2026 06:30 PM')).toEqual({ date: '2026-03-05', time: '18:30' });
    expect(parseDateTime('25/03/2026')).toEqual({ date: '2026-03-25', time: null });
    expect(parseDateTime('2026-03-05T09:00:00Z')).toEqual({ date: '2026-03-05', time: '09:00' });
    expect(parseDateTime('abc')).toBeNull();
  });
  it('数値', () => {
    expect(parseNumber('1,234')).toBe(1234);
    expect(parseNumber('１２３')).toBe(123);
    expect(parseNumber('1.2万')).toBe(12000);
    expect(parseNumber('-')).toBeNull();
    expect(parseNumber('')).toBeNull();
  });
  it('投稿タイプ', () => {
    expect(parseType('Instagramリール')).toBe('reel');
    expect(parseType('IG reel')).toBe('reel');
    expect(parseType('Instagramストーリーズ')).toBe('story');
    expect(parseType('Instagram投稿')).toBe('feed');
    expect(parseType('???')).toBeNull();
  });
});

describe('normalizeTable', () => {
  it('日本語の列名', () => {
    const r = normalizeTable(parseCsv('公開日時,投稿タイプ,説明,リーチ,いいね！,コメント,シェア,保存数\n2026/03/05 18:30,Instagramリール,A,1000,50,5,3,20'));
    expect(r.posts).toHaveLength(1);
    expect(r.posts[0]).toMatchObject({ type: 'reel', reach: 1000, likes: 50, comments: 5, shares: 3, saves: 20, publishedAt: '2026-03-05T18:30', timeKnown: true });
    expect(r.missingOptional).toEqual([]);
  });
  it('英語の列名と揺れ', () => {
    const r = normalizeTable(parseCsv('Publish time,Post type,Description,Reach (accounts),Likes,Comments,Shares,Saves\n03/05/2026 18:30,Reel,B,2000,1,2,3,4'));
    expect(r.posts[0]).toMatchObject({ reach: 2000, saves: 4, type: 'reel' });
  });
  it('日付と時間が別列', () => {
    const r = normalizeTable(parseCsv('日付,時間,リーチ\n2026/03/05,07:10,100'));
    expect(r.posts[0].publishedAt).toBe('2026-03-05T07:10');
    expect(r.missingOptional).toContain('保存');
  });
  it('時刻なしは timeKnown=false', () => {
    expect(normalizeTable(parseCsv('日付,リーチ\n2026/03/05,100')).posts[0].timeKnown).toBe(false);
  });
  it('必須列が無いと MissingColumnsError', () => {
    expect(() => normalizeTable(parseCsv('foo,bar\n1,2'))).toThrow(MissingColumnsError);
  });
  it('手動割り当て', () => {
    const r = normalizeTable(parseCsv('x,y\n2026/03/05 10:00,77'), 'utf-8', { publishedAt: 0, reach: 1 });
    expect(r.posts[0].reach).toBe(77);
  });
  it('読めない行はスキップして数える', () => {
    const r = normalizeTable(parseCsv('公開日時,リーチ\n2026/03/05 10:00,5\nbad,7\n2026/03/06 10:00,-'));
    expect(r.posts).toHaveLength(1);
    expect(r.skippedRows).toBe(2);
  });
});

describe('mergePosts', () => {
  const mk = (caption: string, reach: number) => normalizeTable(parseCsv(`公開日時,説明,リーチ\n2026/03/05 10:00,${caption},${reach}`)).posts[0];
  it('日付＋キャプションが同じなら統合し、新しい数値を採用', () => {
    const a = mergePosts([], [mk('A', 100), mk('B', 50)]);
    const b = mergePosts(a.posts, [mk('A', 150), mk('C', 10)]);
    expect(b.added).toBe(1);
    expect(b.updated).toBe(1);
    expect(b.posts).toHaveLength(3);
    expect(b.posts.find((p) => p.caption === 'A')!.reach).toBe(150);
  });
  it('空白の違いは同じキャプションとみなす', () => {
    expect(mk('A  B', 1).id).toBe(mk('A B', 1).id);
  });
});
