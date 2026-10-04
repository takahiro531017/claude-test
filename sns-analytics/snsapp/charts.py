"""依存ライブラリなしのSVGグラフ(画面でもPDFでもそのまま表示できる)。値は必ず数字ラベルでも読めるようにする。"""
from html import escape

FONT = "'Hiragino Sans','Noto Sans JP','Yu Gothic','Meiryo','IPAGothic',sans-serif"
BLUE, ORANGE, GRAY, GRID, INK = "#2b6cb0", "#dd6b20", "#718096", "#e2e8f0", "#1a202c"
COLORS = [BLUE, ORANGE]


def fmt_int(v):
    return "データなし" if v is None else f"{v:,.0f}"


def fmt_pct(v):
    return "データなし" if v is None else f"{v * 100:.2f}%"


def fmt_dec(v):
    return "データなし" if v is None else f"{v:.2f}"


def _wrap(w, h, body, title):
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{escape(title)}" '
            f'style="max-width:{w}px;font-family:{FONT}"><title>{escape(title)}</title>{body}</svg>')


def no_data(msg="データなし"):
    return _wrap(720, 80, f'<text x="360" y="45" text-anchor="middle" font-size="16" fill="{GRAY}">{escape(msg)}</text>', msg)


def line_chart(labels, series, fmt=fmt_int, title="推移"):
    """series = [(名前, [値 or None, ...]), ...]"""
    vals = [v for _, vs in series for v in vs if v is not None]
    if not vals:
        return no_data()
    W, H, L, R, T, B = 720, 300, 70, 30, 40, 44
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.2 or max(abs(hi) * 0.1, 1)
    lo, hi = (0 if lo >= 0 and lo - pad < 0 else lo - pad), hi + pad
    n = len(labels)
    xs = [L + (W - L - R) * (i / (n - 1) if n > 1 else 0.5) for i in range(n)]
    y = lambda v: T + (H - T - B) * (1 - (v - lo) / (hi - lo))
    out = []
    for k in range(5):
        gv = lo + (hi - lo) * k / 4
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y(gv):.1f}" y2="{y(gv):.1f}" stroke="{GRID}"/>'
                   f'<text x="{L - 8}" y="{y(gv) + 4:.1f}" text-anchor="end" font-size="12" fill="{GRAY}">{escape(fmt(gv))}</text>')
    for x, lab in zip(xs, labels):
        out.append(f'<text x="{x:.1f}" y="{H - 16}" text-anchor="middle" font-size="12" fill="{GRAY}">{escape(str(lab))}</text>')
    for si, (name, vs) in enumerate(series):
        col = COLORS[si % len(COLORS)]
        seg, paths = [], []
        for x, v in zip(xs, vs):
            if v is None:
                if seg:
                    paths.append(seg)
                seg = []
            else:
                seg.append((x, y(v)))
        if seg:
            paths.append(seg)
        for p in paths:
            if len(p) > 1:
                out.append(f'<polyline fill="none" stroke="{col}" stroke-width="2.5" points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in p)}"/>')
        for i, (x, v) in enumerate(zip(xs, vs)):
            if v is None:
                continue
            out.append(f'<circle cx="{x:.1f}" cy="{y(v):.1f}" r="4" fill="{col}"/>')
            if n <= 8 or i == n - 1:
                dy = -10 if si == 0 else 18
                out.append(f'<text x="{x:.1f}" y="{y(v) + dy:.1f}" text-anchor="middle" font-size="12" font-weight="600" fill="{col}">{escape(fmt(v))}</text>')
        if len(series) > 1:
            out.append(f'<rect x="{L + si * 190}" y="10" width="14" height="14" rx="3" fill="{col}"/>'
                       f'<text x="{L + si * 190 + 20}" y="22" font-size="13" fill="{INK}">{escape(name)}</text>')
    return _wrap(W, H, "".join(out), title)


def bar_chart(labels, values, fmt=fmt_int, title="比較", highlight=True):
    """横棒グラフ。いちばん大きい棒をオレンジ(◎)にする。None は「データなし」と表示。"""
    if not labels:
        return no_data()
    W, L, R, rh = 720, 170, 120, 36
    H = rh * len(labels) + 16
    nums = [v for v in values if v is not None]
    if not nums:
        return no_data()
    mx, top = max(max(nums), 1e-9), max(nums)
    out = []
    for i, (lab, v) in enumerate(zip(labels, values)):
        yy = 8 + i * rh
        out.append(f'<text x="{L - 10}" y="{yy + 22}" text-anchor="end" font-size="14" fill="{INK}">{escape(str(lab))}</text>')
        if v is None:
            out.append(f'<text x="{L}" y="{yy + 22}" font-size="13" fill="{GRAY}">データなし</text>')
            continue
        w = max((W - L - R) * (max(v, 0) / mx), 2)
        best = highlight and v == top and len(nums) > 1
        out.append(f'<rect x="{L}" y="{yy + 6}" width="{w:.1f}" height="22" rx="4" fill="{ORANGE if best else BLUE}"/>'
                   f'<text x="{L + w + 8:.1f}" y="{yy + 22}" font-size="13" font-weight="600" fill="{INK}">{escape(fmt(v))}{" ◎" if best else ""}</text>')
    return _wrap(W, H, "".join(out), title)
