import { describe, expect, it } from "vitest";
import { searchProducts } from "@/lib/search";
import { effectivePrice, summarize } from "@/lib/pricing";
import { getProduct } from "@/lib/search";

describe("searchProducts（モックカタログ）", () => {
  it("品番（表記ゆれ込み）", () => {
    const r = searchProducts("ＳＥ－ＷＤ１００");
    expect(r.candidates[0].product.id).toBe("mock-se-wd100");
    expect(r.candidates[0].score).toBe(100);
  });
  it("メーカー＋カテゴリ（洗濯機は洗濯乾燥機を含む）", () => {
    const ids = searchProducts("サンプル電機 洗濯機").candidates.map((c) => c.product.id);
    expect(ids).toEqual(expect.arrayContaining(["mock-se-wd100", "mock-se-wd90", "mock-se-wt70"]));
    expect(ids).not.toContain("mock-se-rf45");
  });
  it("商品名", () => {
    const ids = searchProducts("ドラム式洗濯乾燥機").candidates.map((c) => c.product.id);
    expect(ids).toEqual(expect.arrayContaining(["mock-se-wd100", "mock-se-wd90"]));
    expect(ids).not.toContain("mock-se-wt70");
  });
  it("該当なしは空配列", () => {
    expect(searchProducts("ZZ-9999X").candidates).toEqual([]);
  });
});

describe("pricing", () => {
  it("実質価格は送料・ポイントが取得不可なら null（推測しない）", () => {
    const p = getProduct("mock-se-wd100")!;
    const a = p.prices.find((r) => r.sourceId === "mock-a")!;
    const b = p.prices.find((r) => r.sourceId === "mock-b")!;
    expect(effectivePrice(a)).toBe(248000 - 2480);
    expect(effectivePrice(b)).toBeNull();
  });
  it("サマリーは取得不可の価格を除外", () => {
    const s = summarize(getProduct("mock-se-wd100")!.prices);
    expect(s).toEqual({ min: 248000, max: 255000, avg: 251500, count: 2 });
  });
});
