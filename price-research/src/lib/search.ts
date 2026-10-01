import { MOCK_PRODUCTS } from "./mock/products";
import { modelKey, normalizeText } from "./normalize/text";
import { normalizeQuery, type NormalizedQuery } from "./normalize/query";
import type { Product, SearchCandidate } from "./types";

/** 検索対象カタログ。Phase 2 以降はアダプター結果に差し替える。 */
export function getCatalog(): Product[] {
  return MOCK_PRODUCTS;
}

export function getProduct(id: string): Product | undefined {
  return getCatalog().find((p) => p.id === id);
}

export function scoreProduct(p: Product, q: NormalizedQuery): SearchCandidate | null {
  if (q.kind === "model") {
    const key = modelKey(p.modelNumber);
    let best = 0;
    for (const qk of q.modelKeys) {
      if (key === qk) best = Math.max(best, 100);
      // 末尾の色・仕様違い（NA-LX129DL / NA-LX129DR 等）を近い候補として出す
      else if (key.startsWith(qk) || qk.startsWith(key)) best = Math.max(best, 60);
    }
    return best > 0
      ? { product: p, score: best, reason: best === 100 ? "品番が一致" : "品番が前方一致（派生型番の可能性）" }
      : null;
  }

  if (q.manufacturerId && p.manufacturerId !== q.manufacturerId) return null;
  if (q.categoryId && p.categoryId !== q.categoryId) {
    // 「洗濯機」は「ドラム式洗濯乾燥機」を含む上位カテゴリとして扱う
    const isParent = q.categoryId === "washer" && p.categoryId === "drum-washer-dryer";
    if (!isParent) return null;
  }

  const haystack = normalizeText(`${p.name} ${p.categoryName} ${p.modelNumber}`);
  const missing = q.keywords.filter((k) => !haystack.includes(k));
  if (missing.length > 0) return null;

  let score = 10 + q.keywords.length * 10;
  const reasons: string[] = [];
  if (q.manufacturerId) { score += 20; reasons.push("メーカー一致"); }
  if (q.categoryId) { score += 20; reasons.push("カテゴリ一致"); }
  if (q.keywords.length) reasons.push("キーワード一致");
  return { product: p, score, reason: reasons.join("・") || "全件" };
}

export function searchProducts(raw: string): { query: NormalizedQuery; candidates: SearchCandidate[] } {
  const query = normalizeQuery(raw);
  if (!query.normalized) return { query, candidates: [] };
  const candidates = getCatalog()
    .map((p) => scoreProduct(p, query))
    .filter((c): c is SearchCandidate => c !== null)
    .sort((a, b) => b.score - a.score);
  return { query, candidates };
}
