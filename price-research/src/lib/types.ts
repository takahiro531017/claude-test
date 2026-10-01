/** 取得できなかった値は null とし、UI では必ず「取得不可」と表示する（推測値は入れない）。 */
export type Unavailable = null;

export type PriceKind =
  | "new" // 新品の現在価格
  | "list" // メーカー希望小売価格
  | "used"
  | "refurbished"
  | "outlet"
  | "business"
  | "rental";

export interface PriceRecord {
  kind: PriceKind;
  /** 取得元ID（アダプターID） */
  sourceId: string;
  sourceName: string;
  /** 円。取得不可は null */
  amount: number | null;
  taxIncluded: boolean | null;
  shipping: number | null;
  pointBack: number | null;
  /** 取得元ページ URL（必須） */
  url: string;
  /** ISO 8601（必須） */
  fetchedAt: string;
}

export interface Product {
  id: string;
  manufacturerId: string;
  manufacturerName: string;
  /** 表示用の品番 */
  modelNumber: string;
  name: string;
  categoryId: string;
  categoryName: string;
  releaseDate: string | null;
  releaseSource: string | null;
  specs: Record<string, string | null>;
  prices: PriceRecord[];
  /** 開発用モックデータか */
  isMock: boolean;
}

export interface SearchCandidate {
  product: Product;
  score: number;
  reason: string;
}
