#!/usr/bin/env python3
"""オークローン部品表(xlsx) -> index.html (データ埋め込み)。 usage: PARTS_PASSWORD=... build.py parts.xlsx"""
import sys, json, base64, os, unicodedata, openpyxl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from imgs import extract

def nf(s):  # NFKC（①等の丸数字は部品図の番号なので維持）
    return "".join(c if "\u2460" <= c <= "\u2473" else unicodedata.normalize("NFKC", c) for c in s)

from openpyxl.utils import get_column_letter
wb = openpyxl.load_workbook(sys.argv[1])
zf, IMGS = extract(sys.argv[1])
MIME = {'.jpeg': 'image/jpeg', '.jpg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif'}
images, img_idx = [], {}
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
    # 画像の配置先セル (結合セルなら左上セル) を決める
    placed = {}
    for im in IMGS.get(ws.title, []):
        ext = os.path.splitext(im['media'])[1].lower()
        if ext not in MIME: continue
        data = zf.read(im['media'])
        if len(data) < 200: continue
        r = (im['r0'] + im['r1']) // 2; c = (im['c0'] + im['c1']) // 2
        for m in ws.merged_cells.ranges:
            if m.min_row <= r <= m.max_row and m.min_col <= c <= m.max_col:
                r, c = m.min_row, m.min_col; break
        if im['media'] not in img_idx:
            img_idx[im['media']] = len(images)
            images.append('data:%s;base64,%s' % (MIME[ext], base64.b64encode(data).decode()))
        placed.setdefault((r, c), []).append(img_idx[im['media']])
    # 有効範囲
    maxr = maxc = 0
    for r in range(1, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            if val(r, c):
                maxr, maxc = max(maxr, r), max(maxc, c)
    for (r, c) in placed: maxr, maxc = max(maxr, r), max(maxc, c)
    rows = []
    for r in range(1, maxr + 1):
        cells = []
        for c in range(1, maxc + 1):
            if (r, c) in covered: continue
            rs, cs = merges.get((r, c), (1, 1))
            cs = min(cs, maxc - c + 1); rs = min(rs, maxr - r + 1)
            cells.append([val(r, c), rs, cs, c] + ([placed[(r, c)]] if (r, c) in placed else []))
        # 結合されていない長い文字が右側の空セルへはみ出している場合 (Excel の見た目) は横に広げる
        for i, x in enumerate(cells):
            rest = cells[i + 1:]
            if x[0] and x[1] == 1 and x[2] == 1 and len(x[0]) > 8 and len(x) == 4 and rest \
               and all(not y[0] and y[1] == 1 and y[2] == 1 and len(y) == 4 for y in rest) \
               and rest[-1][3] == x[3] + len(rest):
                x[2] = len(rest) + 1; del cells[i + 1:]
                break
        if any(x[0] or len(x) > 4 for x in cells) or any(x[1] > 1 for x in cells):
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
# 暗号化 (パスワードは環境変数 PARTS_PASSWORD で渡す。リポジトリには保存しない)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
pw = os.environ.get("PARTS_PASSWORD")
if not pw: sys.exit("PARTS_PASSWORD を環境変数で指定してください")
ITER = 600000
salt, iv = os.urandom(16), os.urandom(12)
key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(pw.encode())
payload = json.dumps({"d": sheets, "i": images}, ensure_ascii=False, separators=(",", ":")).encode()
enc = {"salt": base64.b64encode(salt).decode(), "iv": base64.b64encode(iv).decode(), "iter": ITER,
       "data": base64.b64encode(AESGCM(key).encrypt(iv, payload, None)).decode()}
tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.html"), encoding="utf-8").read()
out = tpl.replace("/*ENC*/null", json.dumps(enc))
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"), "w", encoding="utf-8").write(out)
print(len(sheets), "sheets, encrypted")
