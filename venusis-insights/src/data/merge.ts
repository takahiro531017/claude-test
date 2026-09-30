import type { Post } from './types';

/** 既存データに新しいデータを統合する。同じ id（日付＋キャプション）は新しい方の数値で置き換える */
export function mergePosts(existing: Post[], incoming: Post[]): { posts: Post[]; added: number; updated: number } {
  const map = new Map(existing.map((p) => [p.id, p]));
  let added = 0;
  let updated = 0;
  for (const p of incoming) {
    if (map.has(p.id)) updated++;
    else added++;
    map.set(p.id, p);
  }
  const posts = [...map.values()].sort((a, b) => a.publishedAt.localeCompare(b.publishedAt));
  return { posts, added, updated };
}
