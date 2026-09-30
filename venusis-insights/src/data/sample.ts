import { buildPost } from './normalize';
import type { Post, PostType } from './types';

/** 再現性のある疑似乱数 */
function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 0x100000000;
  };
}

const pad = (n: number) => String(n).padStart(2, '0');

const TOPICS: Record<PostType, string[]> = {
  reel: ['朝3分のスキンケア習慣', 'ヘッドスパ前後の比較', '使い方ムービー 初めてのモード切替', 'お風呂上がりのリラックスタイム', '1週間使ってみた変化'],
  feed: ['新色のご紹介', 'お手入れのコツ まとめ', 'ご愛用者さまの声', 'ギフトにおすすめのセット', '季節の乾燥対策ポイント'],
  story: ['今日の使用シーン', 'アンケート: 使う時間帯は？', 'お客さまの投稿をご紹介', '新商品のティザー'],
};

/**
 * サンプル投稿を生成する（実在のデータではありません）。
 * 終了日（end）から約180日さかのぼって、リール＞フィード、平日の夜が強い、という傾向を入れている。
 */
export function generateSample(end: Date = new Date()): Post[] {
  const rand = rng(20260930);
  const posts: Post[] = [];
  const base = new Date(end.getFullYear(), end.getMonth(), end.getDate());
  for (let back = 179; back >= 0; back--) {
    const day = new Date(base.getFullYear(), base.getMonth(), base.getDate() - back);
    const dow = day.getDay(); // 0=日
    // 週4〜5回ペースで投稿
    const r = rand();
    const count = r < 0.55 ? 0 : r < 0.92 ? 1 : 2;
    for (let k = 0; k < count; k++) {
      const tr = rand();
      const type: PostType = tr < 0.4 ? 'reel' : tr < 0.8 ? 'feed' : 'story';
      const hour = type === 'story' ? 8 + Math.floor(rand() * 14) : [8, 12, 13, 18, 20, 21, 22][Math.floor(rand() * 7)];
      const minute = Math.floor(rand() * 60);
      let reach = type === 'reel' ? 5200 : type === 'feed' ? 2100 : 900;
      if (hour >= 20 && hour <= 22) reach *= 1.4;
      else if (hour >= 12 && hour <= 13) reach *= 1.1;
      else if (hour <= 9) reach *= 0.85;
      if (dow >= 1 && dow <= 4) reach *= 1.1;
      if (dow === 0) reach *= 0.85;
      reach *= 0.55 + rand() * 0.95 + (179 - back) / 179 * 0.25; // 少しずつ伸びている
      reach = Math.round(reach);
      const erBase = type === 'reel' ? 0.05 : type === 'feed' ? 0.065 : 0.025;
      const er = erBase * (0.6 + rand() * 0.9);
      const eng = Math.round(reach * er);
      const saves = Math.round(eng * (type === 'feed' ? 0.3 : type === 'reel' ? 0.22 : 0.05) * (0.6 + rand() * 0.8));
      const shares = Math.round(eng * (type === 'reel' ? 0.14 : 0.06) * (0.5 + rand()));
      const comments = Math.round(eng * 0.05 * (0.5 + rand()));
      const likes = Math.max(0, eng - saves - shares - comments);
      const topics = TOPICS[type];
      posts.push(
        buildPost(
          {
            publishedAt: `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}T${pad(hour)}:${pad(minute)}`,
            timeKnown: true,
            caption: `${topics[Math.floor(rand() * topics.length)]} #${posts.length + 1}`,
            type,
            reach,
            likes,
            comments,
            shares,
            saves,
          },
          'sample',
        ),
      );
    }
  }
  return posts;
}
