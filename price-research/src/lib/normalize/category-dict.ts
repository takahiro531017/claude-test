export interface CategoryEntry {
  id: string;
  name: string;
  keywords: string[];
}

/** 長い語を先に判定するため、より具体的なカテゴリを前に置く。 */
export const CATEGORIES: CategoryEntry[] = [
  { id: "drum-washer-dryer", name: "ドラム式洗濯乾燥機", keywords: ["ドラム式洗濯乾燥機", "ドラム式", "ドラム洗濯", "ドラム"] },
  { id: "washer", name: "洗濯機", keywords: ["洗濯機", "全自動洗濯機", "縦型洗濯機", "洗濯乾燥機"] },
  { id: "fridge", name: "冷蔵庫", keywords: ["冷蔵庫", "冷凍庫"] },
  { id: "aircon", name: "エアコン", keywords: ["エアコン", "ルームエアコン", "冷暖房"] },
  { id: "tv", name: "テレビ", keywords: ["テレビ", "tv", "液晶テレビ", "有機el"] },
  { id: "vacuum", name: "掃除機", keywords: ["掃除機", "クリーナー", "ロボット掃除機"] },
  { id: "cooking", name: "調理家電", keywords: ["炊飯器", "電子レンジ", "オーブンレンジ", "ホットプレート", "トースター"] },
  { id: "beauty", name: "美容家電", keywords: ["ドライヤー", "美顔器", "シェーバー", "脱毛器"] },
  { id: "pc-peripheral", name: "PC周辺機器", keywords: ["マウス", "キーボード", "ルーター", "モニター", "プリンター"] },
];
