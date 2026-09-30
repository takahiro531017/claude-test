import { COLUMN_CANDIDATES, FIELD_LABEL, OPTIONAL_FIELDS, TYPE_PATTERNS, type FieldKey } from '../config/columnMap';
import { ImportError, type ImportResult, type Post, type PostSource, type PostType } from './types';

export type ColumnOverrides = Partial<Record<FieldKey, number>>;

export class MissingColumnsError extends ImportError {
  constructor(
    public missing: FieldKey[],
    public headers: string[],
  ) {
    super(`必要な列が見つかりませんでした: ${missing.map((k) => FIELD_LABEL[k]).join('、')}`);
  }
}

/** 照合用に列名をそろえる（全角半角、大文字小文字、空白、記号を無視） */
export function normKey(s: string): string {
  return s
    .normalize('NFKC')
    .toLowerCase()
    .replace(/[\s\u3000!！?？・_\-‐()（）\[\]【】「」:：/／.。,、]/g, '');
}

const NO_CONTAINS_FALLBACK = new Set(['date', 'time', 'type', 'like', 'save', 'share', 'comment', '日付', '時間', '時刻', '種類', 'タイプ', '説明', 'タイトル']);

/** ヘッダー行から、各項目がどの列かを決める */
export function mapColumns(headers: string[], overrides: ColumnOverrides = {}): Partial<Record<FieldKey, number>> {
  const keys = headers.map(normKey);
  const result: Partial<Record<FieldKey, number>> = { ...overrides };
  const used = new Set<number>(Object.values(overrides));
  const fields = Object.keys(COLUMN_CANDIDATES) as FieldKey[];

  // 1回目: 完全一致
  for (const f of fields) {
    if (result[f] !== undefined) continue;
    for (const cand of COLUMN_CANDIDATES[f].map(normKey)) {
      const idx = keys.findIndex((k, i) => k === cand && !used.has(i));
      if (idx >= 0) {
        result[f] = idx;
        used.add(idx);
        break;
      }
    }
  }
  // 2回目: 部分一致（「Reach (accounts)」のような揺れ）
  for (const f of fields) {
    if (result[f] !== undefined) continue;
    for (const cand of COLUMN_CANDIDATES[f].map(normKey)) {
      if (cand.length < 2 || NO_CONTAINS_FALLBACK.has(cand)) continue;
      const idx = keys.findIndex((k, i) => k.includes(cand) && !used.has(i));
      if (idx >= 0) {
        result[f] = idx;
        used.add(idx);
        break;
      }
    }
  }
  return result;
}

export function parseNumber(raw: string | undefined): number | null {
  if (raw === undefined) return null;
  let s = raw.normalize('NFKC').trim().replace(/[,\s]/g, '');
  if (s === '' || s === '-' || s === '--' || s === '—') return null;
  let mult = 1;
  if (s.endsWith('万')) {
    mult = 10000;
    s = s.slice(0, -1);
  } else if (/k$/i.test(s)) {
    mult = 1000;
    s = s.slice(0, -1);
  }
  s = s.replace(/%$/, '');
  const n = Number(s);
  return Number.isFinite(n) ? Math.max(0, Math.round(n * mult)) : null;
}

const pad = (n: number) => String(n).padStart(2, '0');

/** 日付文字列を {date:"YYYY-MM-DD", time:"HH:mm"|null} にする。読めなければ null */
export function parseDateTime(raw: string): { date: string; time: string | null } | null {
  const s = raw.normalize('NFKC').trim();
  if (!s) return null;
  let y: number, mo: number, d: number;
  let rest = '';
  let m = s.match(/^(\d{4})[\/\-.年](\d{1,2})[\/\-.月](\d{1,2})日?(.*)$/);
  if (m) {
    [y, mo, d] = [+m[1], +m[2], +m[3]];
    rest = m[4];
  } else {
    m = s.match(/^(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{4})(.*)$/);
    if (!m) return null;
    let a = +m[1];
    let b = +m[2];
    y = +m[3];
    rest = m[4];
    // 米国式 MM/DD/YYYY を基本とし、月として不可能なときだけ DD/MM にする
    if (a > 12 && b <= 12) [a, b] = [b, a];
    [mo, d] = [a, b];
  }
  if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
  const date = `${y}-${pad(mo)}-${pad(d)}`;
  const t = rest.match(/(\d{1,2}):(\d{2})(?::\d{2})?\s*(AM|PM|午前|午後)?/i);
  if (!t) return { date, time: null };
  let h = +t[1];
  const mi = +t[2];
  const ap = t[3]?.toLowerCase();
  if ((ap === 'pm' || ap === '午後') && h < 12) h += 12;
  if ((ap === 'am' || ap === '午前') && h === 12) h = 0;
  if (h > 23 || mi > 59) return null;
  return { date, time: `${pad(h)}:${pad(mi)}` };
}

export function parseType(raw: string | undefined): PostType | null {
  if (!raw) return null;
  const s = raw.normalize('NFKC').toLowerCase();
  for (const { type, patterns } of TYPE_PATTERNS) {
    if (patterns.some((p) => s.includes(p.toLowerCase()))) return type;
  }
  return null;
}

function fnv(str: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(36);
}

/** 重複判定キー: 日付（分まで）＋キャプション（空白・改行の違いは無視） */
export function makeId(publishedAt: string, caption: string): string {
  return fnv(publishedAt + '|' + caption.normalize('NFKC').replace(/\s+/g, ' ').trim());
}

export function buildPost(
  v: { publishedAt: string; timeKnown: boolean; caption: string; type: PostType; reach: number; likes: number; comments: number; shares: number; saves: number },
  source: PostSource,
): Post {
  return { id: makeId(v.publishedAt, v.caption), source, ...v };
}

/** CSVの表（1行目がヘッダー）を投稿データにする */
export function normalizeTable(
  table: string[][],
  encoding: ImportResult['encoding'] = 'utf-8',
  overrides: ColumnOverrides = {},
): ImportResult {
  if (table.length < 1) throw new ImportError('ファイルが空のようです。');
  const headers = table[0].map((h) => h.trim());
  const cols = mapColumns(headers, overrides);

  const missing: FieldKey[] = [];
  if (cols.reach === undefined) missing.push('reach');
  if (cols.publishedAt === undefined && cols.date === undefined) missing.push('publishedAt');
  if (missing.length) throw new MissingColumnsError(missing, headers);

  const get = (row: string[], f: FieldKey) => (cols[f] === undefined ? undefined : row[cols[f]!]);
  const posts: Post[] = [];
  let skipped = 0;

  for (const row of table.slice(1)) {
    const dtRaw = cols.publishedAt !== undefined ? get(row, 'publishedAt') : undefined;
    let dt = dtRaw ? parseDateTime(dtRaw) : null;
    if (!dt && cols.date !== undefined) {
      const d = parseDateTime(get(row, 'date') ?? '');
      if (d) {
        const tRaw = get(row, 'time');
        const t = tRaw ? parseDateTime('2000-01-01 ' + tRaw.trim())?.time ?? null : null;
        dt = { date: d.date, time: d.time ?? t };
      }
    }
    const reach = parseNumber(get(row, 'reach'));
    if (!dt || reach === null) {
      skipped++;
      continue;
    }
    const caption = (get(row, 'caption') ?? '').trim();
    const type = parseType(get(row, 'type')) ?? 'feed';
    posts.push(
      buildPost(
        {
          publishedAt: `${dt.date}T${dt.time ?? '00:00'}`,
          timeKnown: dt.time !== null,
          caption,
          type,
          reach,
          likes: parseNumber(get(row, 'likes')) ?? 0,
          comments: parseNumber(get(row, 'comments')) ?? 0,
          shares: parseNumber(get(row, 'shares')) ?? 0,
          saves: parseNumber(get(row, 'saves')) ?? 0,
        },
        'csv',
      ),
    );
  }

  const missingOptional = OPTIONAL_FIELDS.filter((f) => cols[f] === undefined).map((f) => FIELD_LABEL[f]);
  return { posts, skippedRows: skipped, missingOptional, encoding };
}
