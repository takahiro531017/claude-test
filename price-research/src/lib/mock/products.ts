import type { Product, PriceRecord } from "../types";

/**
 * 開発用モックデータ。メーカー・品番・価格はすべて架空であり、実在の商品・価格ではない。
 * Phase 2 以降は各取得元アダプターの実データに置き換える。
 */
const FETCHED = "2026-10-01T00:00:00+09:00";

function price(p: Partial<PriceRecord> & Pick<PriceRecord, "kind" | "sourceId" | "sourceName" | "amount">): PriceRecord {
  return {
    taxIncluded: true,
    shipping: null,
    pointBack: null,
    url: `https://example.com/mock/${p.sourceId}`,
    fetchedAt: FETCHED,
    ...p,
  };
}

const common = { manufacturerId: "sample", manufacturerName: "サンプル電機", isMock: true };

export const MOCK_PRODUCTS: Product[] = [
  {
    ...common,
    id: "mock-se-wd100",
    modelNumber: "SE-WD100",
    name: "ドラム式洗濯乾燥機 10kg（モック）",
    categoryId: "drum-washer-dryer",
    categoryName: "ドラム式洗濯乾燥機",
    releaseDate: "2025-09-01",
    releaseSource: "モックデータ",
    specs: { "洗濯容量": "10kg", "乾燥容量": "5kg", "乾燥方式": "ヒートポンプ", "AI自動運転": "あり" },
    prices: [
      price({ kind: "list", sourceId: "mock-maker", sourceName: "モック(メーカー希望)", amount: 300000, taxIncluded: true }),
      price({ kind: "new", sourceId: "mock-a", sourceName: "モックEC-A", amount: 248000, shipping: 0, pointBack: 2480 }),
      price({ kind: "new", sourceId: "mock-b", sourceName: "モックEC-B", amount: 255000, shipping: 3300, pointBack: null }),
      price({ kind: "used", sourceId: "mock-c", sourceName: "モック中古C", amount: null }),
    ],
  },
  {
    ...common,
    id: "mock-se-wd90",
    modelNumber: "SE-WD90",
    name: "ドラム式洗濯乾燥機 9kg（モック）",
    categoryId: "drum-washer-dryer",
    categoryName: "ドラム式洗濯乾燥機",
    releaseDate: "2024-09-01",
    releaseSource: "モックデータ",
    specs: { "洗濯容量": "9kg", "乾燥容量": "4.5kg", "乾燥方式": "ヒートポンプ", "AI自動運転": "なし" },
    prices: [
      price({ kind: "new", sourceId: "mock-a", sourceName: "モックEC-A", amount: 212000, shipping: 0, pointBack: 2120 }),
    ],
  },
  {
    ...common,
    id: "mock-se-wt70",
    modelNumber: "SE-WT70",
    name: "全自動洗濯機 7kg 縦型（モック）",
    categoryId: "washer",
    categoryName: "洗濯機",
    releaseDate: null,
    releaseSource: null,
    specs: { "洗濯容量": "7kg", "乾燥方式": null },
    prices: [
      price({ kind: "new", sourceId: "mock-a", sourceName: "モックEC-A", amount: 58000, shipping: 0, pointBack: null }),
    ],
  },
  {
    ...common,
    id: "mock-se-rf45",
    modelNumber: "SE-RF45",
    name: "冷蔵庫 450L 6ドア（モック）",
    categoryId: "fridge",
    categoryName: "冷蔵庫",
    releaseDate: "2025-03-01",
    releaseSource: "モックデータ",
    specs: { "容量": "450L", "ドア数": "6" },
    prices: [
      price({ kind: "new", sourceId: "mock-b", sourceName: "モックEC-B", amount: 189000, shipping: 0, pointBack: 1890 }),
    ],
  },
];
