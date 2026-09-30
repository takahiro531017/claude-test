/** 依存なしの簡易CSVパーサー。引用符、引用符内の改行・カンマ、CRLF、BOM、区切り文字の自動判定に対応 */
export function parseCsv(text: string): string[][] {
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  // Excel由来の "sep=;" 行は、区切り文字の指定として読み取って取り除く
  const sep = text.match(/^sep=(.)\r?\n/i);
  if (sep) text = text.slice(sep[0].length);
  const delimiter = sep ? sep[1] : detectDelimiter(text);
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else inQuotes = false;
      } else field += c;
      continue;
    }
    if (c === '"' && field === '') inQuotes = true;
    else if (c === delimiter) {
      row.push(field);
      field = '';
    } else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++;
      row.push(field);
      field = '';
      rows.push(row);
      row = [];
    } else field += c;
  }
  if (field !== '' || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  // 完全な空行を除く／Excel由来の "sep=," 行を除く
  const cleaned = rows.filter((r) => r.some((v) => v.trim() !== ''));
  return cleaned;
}

function detectDelimiter(text: string): string {
  // 最初の引用符の外にある1行目で、もっとも多い区切り文字を採用
  const firstLine = firstRecord(text);
  const counts: [string, number][] = [',', '\t', ';'].map((d) => [d, countOutsideQuotes(firstLine, d)]);
  counts.sort((a, b) => b[1] - a[1]);
  return counts[0][1] > 0 ? counts[0][0] : ',';
}

function firstRecord(text: string): string {
  let inQ = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '"') inQ = !inQ;
    else if (!inQ && (c === '\n' || c === '\r')) {
      return text.slice(0, i);
    }
  }
  return text;
}

function countOutsideQuotes(line: string, d: string): number {
  let inQ = false;
  let n = 0;
  for (const c of line) {
    if (c === '"') inQ = !inQ;
    else if (!inQ && c === d) n++;
  }
  return n;
}

export function toCsv(rows: (string | number)[][]): string {
  return rows
    .map((r) =>
      r
        .map((v) => {
          const s = String(v);
          return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
        })
        .join(','),
    )
    .join('\r\n');
}
