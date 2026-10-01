export const UNAVAILABLE = "取得不可";

export function yen(n: number | null): string {
  return n === null ? UNAVAILABLE : `¥${n.toLocaleString("ja-JP")}`;
}

export function dateJa(iso: string | null): string {
  if (!iso) return UNAVAILABLE;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? UNAVAILABLE : d.toLocaleDateString("ja-JP", { timeZone: "Asia/Tokyo" });
}

export function dateTimeJa(iso: string): string {
  return new Date(iso).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" });
}

export const KIND_LABEL: Record<string, string> = {
  new: "新品", list: "メーカー希望小売価格", used: "中古", refurbished: "整備済み",
  outlet: "アウトレット", business: "法人向け", rental: "レンタル/サブスク",
};
