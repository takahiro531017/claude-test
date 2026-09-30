// 使い方: npx vite-node scripts/make-sample-csv.ts
// Meta Business Suite風の列名で、サンプルCSV（日本語列名・UTF-8）を public/sample/ に書き出す
import { writeFileSync } from 'node:fs';
import { toCsv } from '../src/data/csv';
import { generateSample } from '../src/data/sample';
import { POST_TYPE_LABEL } from '../src/data/types';

const TYPE_CSV = { reel: 'Instagramリール', feed: 'Instagram投稿', story: 'Instagramストーリーズ' } as const;
const posts = generateSample(new Date(2026, 8, 30));
const rows: (string | number)[][] = [['公開日時', '投稿タイプ', '説明', 'リーチ', 'いいね！', 'コメント', 'シェア', '保存数']];
for (const p of posts) {
  const [d, t] = p.publishedAt.split('T');
  rows.push([`${d.replace(/-/g, '/')} ${t}`, TYPE_CSV[p.type], p.caption, p.reach, p.likes, p.comments, p.shares, p.saves]);
}
writeFileSync('public/sample/sample-posts.csv', '﻿' + toCsv(rows) + '\r\n');
console.log(`${posts.length} rows`, Object.values(POST_TYPE_LABEL).join('/'));
