#!/usr/bin/env python3
"""オークローン部品表(xlsx) -> index.html (データ埋め込み)。 usage: build.py parts.xlsx"""
import sys, json, unicodedata, openpyxl

def nf(s):  # NFKC（①等の丸数字は部品図の番号なので維持）
    return "".join(c if "\u2460" <= c <= "\u2473" else unicodedata.normalize("NFKC", c) for c in s)

from openpyxl.utils import get_column_letter
wb = openpyxl.load_workbook(sys.argv[1])
sheets = []
for ws in wb:
    merges = {}
    covered = set()
    for m in ws.merged_cells.ranges:
        merges[(m.min_row, m.min_col)] = (m.max_row - m.min_row + 1, m.max_col - m.min_col + 1)
        for r in range(m.min_row, m.max_row + 1):
            for c in range(m.min_col, m.max_col + 1):
                if (r, c) != (m.min_row, m.min_col): covered.add((r, c))
    def val(r, c):
        v = ws.cell(r, c).value
        if v is None: return ""
        if isinstance(v, float) and v.is_integer(): v = int(v)
        if isinstance(v, int) and abs(v) >= 1000 and len(str(v)) < 9: return f"{v:,}"
        return nf(str(v)).strip()
    # 有効範囲
    maxr = maxc = 0
    for r in range(1, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            if val(r, c):
                maxr, maxc = max(maxr, r), max(maxc, c)
    rows = []
    for r in range(1, maxr + 1):
        cells = []
        for c in range(1, maxc + 1):
            if (r, c) in covered: continue
            rs, cs = merges.get((r, c), (1, 1))
            cs = min(cs, maxc - c + 1); rs = min(rs, maxr - r + 1)
            cells.append([val(r, c), rs, cs])
        if any(x[0] for x in cells) or any(x[1] > 1 for x in cells):
            rows.append({"r": r, "c": cells})
        else:
            rows.append({"r": r, "c": None})
    # 空行は圧縮(連続空行を1つに)、ただし rowspan に巻き込まれる行は残す
    keep = []
    for i, row in enumerate(rows):
        if row["c"] is None:
            spanned = any(rr["c"] and any(x[1] > 1 and rr["r"] + x[1] > row["r"] > rr["r"] for x in rr["c"]) for rr in rows[max(0, i - 40):i])
            if spanned: row["c"] = []; keep.append(row)
            continue
        keep.append(row)
    sheets.append({"name": nf(ws.title).strip(), "rows": [{"r": k["r"], "c": k["c"]} for k in keep]})
tpl = open(__file__.replace("build.py", "template.html"), encoding="utf-8").read()
out = tpl.replace("/*DATA*/null", json.dumps(sheets, ensure_ascii=False, separators=(",", ":")))
open(__file__.replace("build.py", "index.html"), "w", encoding="utf-8").write(out)
print(len(sheets), "sheets")
