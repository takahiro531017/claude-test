/** 各種ダッシュ・長音風の記号を ASCII ハイフンへ。NFKC 後に残るものを対象にする。 */
const DASHES = /[‐-―−ー－⁃]/g;

/** 全角半角統一・小文字化・空白正規化。品番判定前の共通前処理。 */
export function normalizeText(input: string): string {
  return input
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[　\s]+/g, " ")
    .trim();
}

/** 品番比較用キー。ハイフン・空白・記号を除去し大文字化（NA-LX129DL → NALX129DL）。 */
export function modelKey(input: string): string {
  return input
    .normalize("NFKC")
    .replace(DASHES, "-")
    .replace(/[-\s._/・]/g, "")
    .toUpperCase();
}

/** ハイフン統一済みトークン（長音「ー」は品番候補の判定時のみ変換するため別関数）。 */
export function unifyDashes(input: string): string {
  return input.replace(DASHES, "-");
}
