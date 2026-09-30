import { TIME_BANDS } from '../config/columnMap';
import { POST_TYPE_LABEL, type Post } from '../data/types';
import { byType, heatmap, WEEKDAYS } from './groupings';
import { deltaPercent, engagement, fmtCompact, fmtInt, fmtPct, parseLocal, summarize } from './metrics';

export type InsightKind = '成果' | '比較' | '時間帯' | '保存' | '注目投稿' | '次にやること' | '注意';
export interface Insight {
  kind: InsightKind;
  text: string;
}

const MIN_PER_TYPE = 3;
const MIN_PER_CELL = 2;

const bandShort = (i: number) => TIME_BANDS[i].label.split(' ')[0];
const clip = (s: string, n = 18) => (s.length > n ? s.slice(0, n) + '…' : s);
const ratio = (r: number) => (r >= 10 ? r.toFixed(0) : r.toFixed(1));

/** データから気づきの文章を作る。件数が少ないときは言い切らず、注意書きを付ける */
export function buildInsights(current: Post[], previous: Post[] | null): Insight[] {
  if (current.length === 0) return [{ kind: '注意', text: 'この期間の投稿データがありません。「データ入力」からCSVを読み込んでください。' }];

  const out: Insight[] = [];
  const cur = summarize(current);
  if (current.length < 10) out.push({ kind: '注意', text: `対象の投稿が${current.length}件とまだ少ないため、以下は参考程度にご覧ください。` });

  // 1. 成果の変化
  if (previous && previous.length > 0) {
    const prev = summarize(previous);
    const d = deltaPercent(cur.totalReach, prev.totalReach);
    if (d.dir === 'up') out.push({ kind: '成果', text: `合計リーチは前の期間より${d.text.replace(/^▲ \+/, '')}増えました（${fmtInt(prev.totalReach)} → ${fmtInt(cur.totalReach)}）。` });
    else if (d.dir === 'down') out.push({ kind: '成果', text: `合計リーチは前の期間より${d.text.replace(/^▼ −/, '')}減りました（${fmtInt(prev.totalReach)} → ${fmtInt(cur.totalReach)}）。投稿数の増減もあわせて確認しましょう。` });
    else if (d.dir === 'flat') out.push({ kind: '成果', text: '合計リーチは前の期間とほぼ同じです。' });
    if (cur.er !== null && prev.er !== null && Math.abs(cur.er - prev.er) >= 0.0005) {
      const up = cur.er > prev.er;
      out.push({ kind: '成果', text: `エンゲージメント率は${fmtPct(prev.er)}から${fmtPct(cur.er)}に${up ? '上がりました' : '下がりました'}。` });
    }
  }

  // 2. リール vs フィード
  const types = byType(current);
  const reel = types.find((t) => t.type === 'reel')!;
  const feed = types.find((t) => t.type === 'feed')!;
  let bestFormat: 'reel' | 'feed' | null = null;
  if (reel.count >= MIN_PER_TYPE && feed.count >= MIN_PER_TYPE && reel.avgReach && feed.avgReach) {
    const r = reel.avgReach / feed.avgReach;
    if (r >= 1.15) {
      bestFormat = 'reel';
      out.push({ kind: '比較', text: `リールの平均リーチはフィードの${ratio(r)}倍です（リール ${fmtInt(reel.avgReach)}、フィード ${fmtInt(feed.avgReach)}）。新しい人に届けたいときはリールが向いています。` });
    } else if (r <= 1 / 1.15) {
      bestFormat = 'feed';
      out.push({ kind: '比較', text: `フィードの平均リーチはリールの${ratio(1 / r)}倍です（フィード ${fmtInt(feed.avgReach)}、リール ${fmtInt(reel.avgReach)}）。` });
    } else out.push({ kind: '比較', text: `リールとフィードの平均リーチはほぼ同じです（リール ${fmtInt(reel.avgReach)}、フィード ${fmtInt(feed.avgReach)}）。` });
  } else {
    out.push({ kind: '注意', text: `リールとフィードの比較には、それぞれ${MIN_PER_TYPE}件以上の投稿が必要です（今はリール${reel.count}件、フィード${feed.count}件）。` });
  }

  // 3. 時間帯
  const cells = heatmap(current).flat().filter((c) => c.count >= MIN_PER_CELL && c.avgReach !== null);
  let bestSlot: string | null = null;
  if (cells.length >= 2) {
    const best = cells.reduce((a, b) => (b.avgReach! > a.avgReach! ? b : a));
    const all = cells.reduce((s, c) => s + c.avgReach! * c.count, 0) / cells.reduce((s, c) => s + c.count, 0);
    bestSlot = `${WEEKDAYS[best.day]}曜の${bandShort(best.band)}`;
    out.push({ kind: '時間帯', text: `届きやすい時間帯は${bestSlot}です（平均リーチ ${fmtInt(best.avgReach!)}、全体平均の${ratio(best.avgReach! / all)}倍・${best.count}件）。` });
  } else {
    out.push({ kind: '注意', text: '曜日×時間帯の分析には、同じ時間帯の投稿が2件以上ある枠が必要です。投稿を重ねるとここに結果が出ます。' });
  }

  // 4. 保存率
  const withSave = types.filter((t) => t.type !== 'story' && t.count >= MIN_PER_TYPE && t.saveRate !== null);
  if (withSave.length >= 2) {
    const best = withSave.reduce((a, b) => (b.saveRate! > a.saveRate! ? b : a));
    out.push({ kind: '保存', text: `保存されやすいのは${POST_TYPE_LABEL[best.type]}です（保存率 ${fmtPct(best.saveRate, 2)}）。「役に立つ」と感じてもらえる内容は、保存につながります。` });
  }

  // 5. 注目投稿
  const top = [...current].sort((a, b) => b.reach - a.reach)[0];
  const d = parseLocal(top.publishedAt);
  const er = top.reach > 0 ? engagement(top) / top.reach : null;
  out.push({ kind: '注目投稿', text: `最もリーチが多かったのは${d.getMonth() + 1}月${d.getDate()}日の${POST_TYPE_LABEL[top.type]}${top.caption ? `「${clip(top.caption)}」` : ''}です（リーチ ${fmtCompact(top.reach)}${er !== null ? `、エンゲージメント率 ${fmtPct(er)}` : ''}）。内容や見せ方を次の投稿に活かしましょう。` });

  // 6. 次にやること
  const fmtName = bestFormat ? POST_TYPE_LABEL[bestFormat] : null;
  if (fmtName && bestSlot) out.push({ kind: '次にやること', text: `次の1か月は、${bestSlot}に${fmtName}を投稿してみましょう。結果は次回のCSVで確認できます。` });
  else if (fmtName) out.push({ kind: '次にやること', text: `次の1か月は、${fmtName}の投稿を増やして反応を比べてみましょう。` });
  else if (bestSlot) out.push({ kind: '次にやること', text: `次の1か月は、${bestSlot}の投稿を増やして反応を比べてみましょう。` });
  else out.push({ kind: '次にやること', text: 'まずはリールとフィードを、いろいろな曜日・時間帯で投稿してデータを増やしましょう。' });

  return out;
}
