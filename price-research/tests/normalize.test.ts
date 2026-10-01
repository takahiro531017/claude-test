import { describe, expect, it } from "vitest";
import { modelKey, normalizeText } from "@/lib/normalize/text";
import { normalizeQuery } from "@/lib/normalize/query";

describe("normalizeText / modelKey", () => {
  it("全角半角・大文字小文字を統一する", () => {
    expect(normalizeText("　ＮＡ－ＬＸ１２９ＤＬ  ")).toBe("na-lx129dl");
  });
  it.each(["NA-LX129DL", "na-lx129dl", "ＮＡ－ＬＸ１２９ＤＬ", "NA LX129DL", "NA−LX129DL", "NALX129DL"])(
    "表記ゆれ %s は同一キー",
    (s) => expect(modelKey(s)).toBe("NALX129DL"),
  );
});

describe("normalizeQuery", () => {
  it("品番を判定する", () => {
    const q = normalizeQuery("ＮＡ－ＬＸ１２９ＤＬ");
    expect(q.kind).toBe("model");
    expect(q.modelKeys).toEqual(["NALX129DL"]);
  });
  it("長音が英数字に挟まれたらハイフン扱い", () => {
    expect(normalizeQuery("NAーLX129DL").modelKeys).toEqual(["NALX129DL"]);
  });
  it("メーカー＋カテゴリを判定し、日英表記を吸収する", () => {
    for (const s of ["パナソニック 洗濯機", "Panasonic 洗濯機", "ＰＡＮＡＳＯＮＩＣ　洗濯機"]) {
      const q = normalizeQuery(s);
      expect(q.manufacturerId).toBe("panasonic");
      expect(q.categoryId).toBe("washer");
      expect(q.kind).toBe("keyword");
      expect(q.keywords).toEqual([]);
    }
  });
  it("メーカー名のみは maker", () => {
    expect(normalizeQuery("日立").kind).toBe("maker");
    expect(normalizeQuery("hitachi").manufacturerId).toBe("hitachi");
  });
  it("商品名（カテゴリ語）はキーワード扱い", () => {
    const q = normalizeQuery("ドラム式洗濯乾燥機");
    expect(q.kind).toBe("keyword");
    expect(q.categoryId).toBe("drum-washer-dryer");
  });
  it("長音を含む日本語は壊さない", () => {
    expect(normalizeQuery("ドライヤー").categoryId).toBe("beauty");
  });
  it("英字のみ・数字のみは品番扱いしない", () => {
    expect(normalizeQuery("sharp").modelKeys).toEqual([]);
    expect(normalizeQuery("2024").modelKeys).toEqual([]);
  });
  it("空入力", () => {
    expect(normalizeQuery("   ").normalized).toBe("");
  });
});
