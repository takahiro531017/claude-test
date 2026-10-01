export interface ManufacturerEntry {
  id: string;
  /** 表示名 */
  name: string;
  /** 別表記（日本語・英語・略称）。正規化済み（小文字・NFKC）で比較される。 */
  aliases: string[];
}

export const MANUFACTURERS: ManufacturerEntry[] = [
  { id: "panasonic", name: "パナソニック", aliases: ["パナソニック", "panasonic", "ぱなそにっく", "パナ"] },
  { id: "hitachi", name: "日立", aliases: ["日立", "ひたち", "ヒタチ", "hitachi", "日立グローバルライフソリューションズ"] },
  { id: "sharp", name: "シャープ", aliases: ["シャープ", "sharp", "しゃーぷ"] },
  { id: "toshiba", name: "東芝", aliases: ["東芝", "とうしば", "トウシバ", "toshiba"] },
  { id: "mitsubishi", name: "三菱電機", aliases: ["三菱電機", "三菱", "mitsubishi", "mitsubishi electric"] },
  { id: "daikin", name: "ダイキン", aliases: ["ダイキン", "daikin"] },
  { id: "sony", name: "ソニー", aliases: ["ソニー", "sony"] },
  { id: "aqua", name: "AQUA", aliases: ["aqua", "アクア"] },
  { id: "dyson", name: "ダイソン", aliases: ["ダイソン", "dyson"] },
  { id: "tiger", name: "タイガー", aliases: ["タイガー", "tiger", "タイガー魔法瓶"] },
  { id: "zojirushi", name: "象印", aliases: ["象印", "ぞうじるし", "zojirushi"] },
  { id: "balmuda", name: "バルミューダ", aliases: ["バルミューダ", "balmuda"] },
  { id: "iris", name: "アイリスオーヤマ", aliases: ["アイリスオーヤマ", "アイリス", "iris ohyama", "irisohyama"] },
  { id: "haier", name: "ハイアール", aliases: ["ハイアール", "haier"] },
  { id: "lg", name: "LG", aliases: ["lg", "エルジー"] },
  { id: "samsung", name: "サムスン", aliases: ["サムスン", "samsung"] },
  { id: "anker", name: "Anker", aliases: ["anker", "アンカー"] },
  { id: "logicool", name: "ロジクール", aliases: ["ロジクール", "logicool", "logitech", "ロジテック"] },
  { id: "buffalo", name: "バッファロー", aliases: ["バッファロー", "buffalo"] },
  { id: "elecom", name: "エレコム", aliases: ["エレコム", "elecom"] },
  // 開発用モックデータ専用の架空メーカー（実在しない）
  { id: "sample", name: "サンプル電機", aliases: ["サンプル電機", "sample", "sample electric", "さんぷる"] },
];
