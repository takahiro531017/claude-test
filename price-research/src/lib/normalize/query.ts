import { CATEGORIES } from "./category-dict";
import { MANUFACTURERS } from "./manufacturer-dict";
import { modelKey, normalizeText, unifyDashes } from "./text";

export type QueryKind = "model" | "maker" | "keyword";

export interface NormalizedQuery {
  raw: string;
  /** NFKC・小文字化後の文字列 */
  normalized: string;
  kind: QueryKind;
  /** 品番候補（modelKey 形式：ハイフン無し・大文字） */
  modelKeys: string[];
  manufacturerId?: string;
  categoryId?: string;
  /** メーカー名・カテゴリ語・品番を除いた残りの語 */
  keywords: string[];
}

/** 英字と数字を両方含み、4文字以上の英数字（ハイフン等区切り可）を品番候補とみなす。 */
function isModelToken(token: string): boolean {
  const t = unifyDashes(token);
  if (!/^[a-z0-9]+(?:[-_./][a-z0-9]+)*$/.test(t)) return false;
  const key = modelKey(t);
  return key.length >= 4 && /[A-Z]/.test(key) && /[0-9]/.test(key);
}

function findManufacturer(tokens: string[], normalized: string): { id: string; consumed: string[] } | undefined {
  for (const m of MANUFACTURERS) {
    for (const alias of m.aliases) {
      const a = normalizeText(alias);
      const ascii = /^[\x00-\x7f]+$/.test(a);
      if (ascii) {
        // 英語表記は単語一致（"lg" が他の語に含まれる誤検出を避ける）
        const words = a.split(" ");
        if (words.length === 1) {
          if (tokens.includes(a)) return { id: m.id, consumed: [a] };
        } else if (normalized.includes(a)) {
          return { id: m.id, consumed: words };
        }
      } else if (normalized.includes(a)) {
        return { id: m.id, consumed: [a] };
      }
    }
  }
  return undefined;
}

function findCategory(normalized: string): { id: string; keyword: string } | undefined {
  for (const c of CATEGORIES) {
    for (const k of c.keywords) {
      if (normalized.includes(normalizeText(k))) return { id: c.id, keyword: normalizeText(k) };
    }
  }
  return undefined;
}

export function normalizeQuery(raw: string): NormalizedQuery {
  const normalized = normalizeText(unifyDashesPreservingKana(raw));
  const tokens = normalized.split(" ").filter(Boolean);

  const modelKeys = tokens.filter(isModelToken).map(modelKey);
  const maker = findManufacturer(tokens, normalized);
  const category = findCategory(normalized);

  let rest = tokens.filter((t) => !isModelToken(t));
  if (maker) {
    rest = rest
      .map((t) => maker.consumed.reduce((acc, c) => acc.split(c).join(""), t))
      .filter(Boolean);
  }
  if (category) {
    rest = rest.map((t) => t.split(category.keyword).join("")).filter(Boolean);
  }

  let kind: QueryKind = "keyword";
  if (modelKeys.length > 0) kind = "model";
  else if (maker && !category && rest.length === 0) kind = "maker";

  return {
    raw,
    normalized,
    kind,
    modelKeys,
    manufacturerId: maker?.id,
    categoryId: category?.id,
    keywords: rest,
  };
}

/**
 * 「ー」（長音）は日本語では保持したいので、英数字に挟まれた場合のみハイフン扱いにする。
 * 例: "NAーLX129DL" → "NA-LX129DL" / "ドライヤー" はそのまま。
 */
function unifyDashesPreservingKana(input: string): string {
  const s = input.normalize("NFKC");
  return s
    .replace(/(?<=[A-Za-z0-9])[ー](?=[A-Za-z0-9])/g, "-")
    .replace(/[‐-―−－⁃]/g, "-");
}
