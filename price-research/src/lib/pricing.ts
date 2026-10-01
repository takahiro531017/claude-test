import type { PriceRecord } from "./types";

/** 送料込み・ポイント還元差引後の実質価格。いずれかが取得不可なら null（推測しない）。 */
export function effectivePrice(p: PriceRecord): number | null {
  if (p.amount === null || p.shipping === null || p.pointBack === null) return null;
  return p.amount + p.shipping - p.pointBack;
}

export function summarize(prices: PriceRecord[]) {
  const nums = prices.filter((p) => p.kind === "new" && p.amount !== null).map((p) => p.amount as number);
  if (nums.length === 0) return { min: null, max: null, avg: null, count: 0 };
  const sum = nums.reduce((a, b) => a + b, 0);
  return { min: Math.min(...nums), max: Math.max(...nums), avg: Math.round(sum / nums.length), count: nums.length };
}
