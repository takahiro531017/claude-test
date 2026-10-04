"""Tkinter GUI。重い処理（読み取り）は別スレッドで行い、画面は固めない。"""
from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from shiire_check import __version__, excel_io
from shiire_check.config import get_api_key, load_config, setup_logging
from shiire_check.imaging import render_page, shrink
from shiire_check.matcher import CATEGORIES, REVIEW, ResultRow, summarize
from shiire_check.pipeline import Cancelled
from shiire_check.reader import ClaudeReader, MockReader
from shiire_check.schema import CONFIDENCE_JA
from shiire_check.service import CheckSession, ColumnSelection

log = logging.getLogger(__name__)

NONE_CHOICE = "（使わない）"
COLORS = {"一致": "#d9f0dd", "伝票なし": "#fff7b3", "一覧にない": "#f8c9c9", "要確認": "#ffd9a8"}
WARN_COLOR = "#f0e68c"
FILTERS = ["すべて", *CATEGORIES, "警告あり", "未確認のみ"]

PRIVACY_TEXT = (
    "【データの取り扱いについて】\n"
    "・伝票画像と仕入一覧表は、このパソコン内にのみ保存されます（読み取り結果のキャッシュ・修正・確認済みの記録は"
    "ローカルのSQLiteファイル）。\n"
    "・外部へ送信されるのは、AI読み取り時の「伝票画像」のAnthropic APIへの送信のみです。"
    "仕入一覧表（Excel）の内容は送信されません。\n"
    "・「テスト用（AIを使わない）」モードでは、何も送信されません。\n"
    "・ログにはファイル名と件数程度しか記録しません（伝票番号・金額は記録しません）。"
)


class App(tk.Tk):
    def __init__(self, cfg: dict | None = None):
        super().__init__()
        self.cfg = cfg or load_config()
        setup_logging(self.cfg)
        self.session = CheckSession(self.cfg)
        self.title(f"仕入伝票チェックツール（試作版） v{__version__}")
        self.geometry("1280x800")
        self.minsize(1000, 640)

        self.q: queue.Queue = queue.Queue()
        self.cancel_ev = threading.Event()
        self.worker: threading.Thread | None = None
        self.headers: list[str] = []
        self.shown: list[ResultRow] = []         # 現在表示中の行（ツリーのiid=インデックス）
        self._photo = None
        self._img_cache: tuple[str, Image.Image] | None = None

        self.v_folder = tk.StringVar()
        self.v_excel = tk.StringVar()
        self.v_sheet = tk.StringVar()
        self.v_header_row = tk.IntVar(value=1)
        self.v_num = tk.StringVar()
        self.v_maker = tk.StringVar(value=NONE_CHOICE)
        self.v_date = tk.StringVar(value=NONE_CHOICE)
        self.v_amount = tk.StringVar(value=NONE_CHOICE)
        self.v_mock = tk.BooleanVar(value=False)
        self.v_filter = tk.StringVar(value="すべて")
        self.v_status = tk.StringVar(value="フォルダと仕入一覧表を選んで「照合開始」を押してください。")
        self.v_summary = tk.StringVar()
        self.v_manual = tk.StringVar()
        self.v_confirmed = tk.BooleanVar()
        self.v_memo = tk.StringVar()

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll)

    # ------------------------------------------------------------------ 画面構築
    def _build(self):
        menubar = tk.Menu(self)
        helpm = tk.Menu(menubar, tearoff=0)
        helpm.add_command(label="データの取り扱い・設定について", command=self._about)
        menubar.add_cascade(label="ヘルプ", menu=helpm)
        self.config(menu=menubar)

        top = ttk.LabelFrame(self, text="1. 入力")
        top.pack(fill="x", padx=8, pady=(8, 4))
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="伝票フォルダ").grid(row=0, column=0, sticky="e", padx=4, pady=2)
        ttk.Entry(top, textvariable=self.v_folder).grid(row=0, column=1, columnspan=6, sticky="ew", pady=2)
        ttk.Button(top, text="選択…", command=self._pick_folder).grid(row=0, column=7, padx=4)

        ttk.Label(top, text="仕入一覧表(Excel)").grid(row=1, column=0, sticky="e", padx=4, pady=2)
        ttk.Entry(top, textvariable=self.v_excel).grid(row=1, column=1, sticky="ew", pady=2)
        ttk.Label(top, text="シート").grid(row=1, column=2, sticky="e", padx=(8, 2))
        self.cb_sheet = ttk.Combobox(top, textvariable=self.v_sheet, state="readonly", width=16)
        self.cb_sheet.grid(row=1, column=3, sticky="w")
        self.cb_sheet.bind("<<ComboboxSelected>>", lambda e: self._load_headers())
        ttk.Label(top, text="見出し行").grid(row=1, column=4, sticky="e", padx=(8, 2))
        sp = ttk.Spinbox(top, from_=1, to=50, textvariable=self.v_header_row, width=4, command=self._load_headers)
        sp.grid(row=1, column=5, sticky="w")
        sp.bind("<FocusOut>", lambda e: self._load_headers())
        ttk.Button(top, text="選択…", command=self._pick_excel).grid(row=1, column=7, padx=4)

        cols = ttk.Frame(top)
        cols.grid(row=2, column=0, columnspan=8, sticky="ew", pady=2)
        self.cb_num = self._col_combo(cols, "伝票番号の列（必須）", self.v_num, 0)
        self.cb_maker = self._col_combo(cols, "メーカー名の列", self.v_maker, 1)
        self.cb_date = self._col_combo(cols, "日付の列", self.v_date, 2)
        self.cb_amount = self._col_combo(cols, "金額の列", self.v_amount, 3)

        ctl = ttk.Frame(top)
        ctl.grid(row=3, column=0, columnspan=8, sticky="ew", pady=4)
        self.btn_start = ttk.Button(ctl, text="照合開始", command=self._start)
        self.btn_start.pack(side="left", padx=4)
        self.btn_cancel = ttk.Button(ctl, text="中止", command=self._cancel, state="disabled")
        self.btn_cancel.pack(side="left")
        self.btn_export = ttk.Button(ctl, text="結果をExcelに出力", command=self._export, state="disabled")
        self.btn_export.pack(side="left", padx=8)
        ttk.Checkbutton(ctl, text="テスト用（AIを使わない）", variable=self.v_mock).pack(side="left", padx=8)
        self.progress = ttk.Progressbar(ctl, length=260, mode="determinate")
        self.progress.pack(side="left", padx=8)
        ttk.Label(ctl, textvariable=self.v_status).pack(side="left", padx=4)

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=4)

        left = ttk.Frame(body)
        body.add(left, weight=3)
        fr = ttk.Frame(left)
        fr.pack(fill="x")
        ttk.Label(fr, text="表示:").pack(side="left")
        cb = ttk.Combobox(fr, textvariable=self.v_filter, values=FILTERS, state="readonly", width=12)
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda e: self._refresh())
        ttk.Label(fr, textvariable=self.v_summary).pack(side="left", padx=12)
        ttk.Label(fr, text="（✓列をクリックで確認済み）", foreground="gray").pack(side="right")

        cols_def = [("chk", "確認", 44), ("cat", "区分", 200), ("num", "伝票番号", 150),
                    ("maker", "メーカー名", 130), ("note", "備考", 420)]
        self.tree = ttk.Treeview(left, columns=[c[0] for c in cols_def], show="headings", selectmode="browse")
        for cid, text, w in cols_def:
            self.tree.heading(cid, text=text)
            self.tree.column(cid, width=w, anchor="center" if cid == "chk" else "w", stretch=(cid == "note"))
        for cat, color in COLORS.items():
            self.tree.tag_configure(cat, background=color)
        self.tree.tag_configure("warn", background=WARN_COLOR)
        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        self.tree.bind("<Button-1>", self._on_click)

        right = ttk.Frame(body)
        body.add(right, weight=2)
        self.canvas = tk.Canvas(right, background="#808080", height=340, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._draw_preview())
        self.txt = tk.Text(right, height=10, wrap="word", state="disabled", background="#f7f7f7")
        self.txt.pack(fill="x", pady=4)

        edit = ttk.LabelFrame(right, text="伝票番号の手修正")
        edit.pack(fill="x", pady=2)
        self.ent_manual = ttk.Entry(edit, textvariable=self.v_manual)
        self.ent_manual.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        self.ent_manual.bind("<Return>", lambda e: self._apply_manual())
        self.btn_fix = ttk.Button(edit, text="修正して再照合", command=self._apply_manual)
        self.btn_fix.grid(row=0, column=1, padx=2)
        self.btn_unfix = ttk.Button(edit, text="修正を取り消す", command=self._clear_manual)
        self.btn_unfix.grid(row=0, column=2, padx=2)
        edit.columnconfigure(0, weight=1)

        conf = ttk.Frame(right)
        conf.pack(fill="x", pady=2)
        self.chk_conf = ttk.Checkbutton(conf, text="確認済み", variable=self.v_confirmed, command=self._save_state)
        self.chk_conf.pack(side="left", padx=4)
        ttk.Label(conf, text="担当者メモ").pack(side="left", padx=(12, 2))
        self.ent_memo = ttk.Entry(conf, textvariable=self.v_memo)
        self.ent_memo.pack(side="left", fill="x", expand=True)
        self.ent_memo.bind("<FocusOut>", lambda e: self._save_state())
        self.ent_memo.bind("<Return>", lambda e: self._save_state())

        ttk.Label(self, text="※ 伝票画像はAI読み取り時にAnthropic APIへ送信されます。それ以外の外部送信・外部保存はありません。",
                  foreground="gray").pack(fill="x", padx=10, pady=(0, 4))
        self._set_detail_enabled(False)

    def _col_combo(self, parent, label, var, i):
        ttk.Label(parent, text=label).grid(row=0, column=i * 2, sticky="e", padx=(8, 2))
        cb = ttk.Combobox(parent, textvariable=var, state="readonly", width=22)
        cb.grid(row=0, column=i * 2 + 1, sticky="w")
        return cb

    # ------------------------------------------------------------------ 入力
    def _pick_folder(self):
        d = filedialog.askdirectory(title="伝票フォルダを選択")
        if d:
            self.v_folder.set(d)

    def _pick_excel(self):
        p = filedialog.askopenfilename(title="仕入一覧表を選択", filetypes=[("Excelブック", "*.xlsx")])
        if not p:
            return
        self.v_excel.set(p)
        try:
            sheets = excel_io.list_sheets(p)
        except Exception as e:
            messagebox.showerror("エラー", f"Excelを開けません。\n{e}")
            return
        self.cb_sheet["values"] = sheets
        self.v_sheet.set(sheets[0])
        self._load_headers()

    def _load_headers(self):
        path = self.v_excel.get()
        if not path:
            return
        try:
            hr = max(1, int(self.v_header_row.get()))
            self.headers = excel_io.read_headers(path, self.v_sheet.get() or None, hr)
        except Exception as e:
            messagebox.showerror("エラー", f"見出し行を読めません。\n{e}")
            return
        self.cb_num["values"] = self.headers
        opt = [NONE_CHOICE, *self.headers]
        for cb in (self.cb_maker, self.cb_date, self.cb_amount):
            cb["values"] = opt
        self._guess_columns()

    def _guess_columns(self):
        """見出しに特定の語があれば仮選択する（変更は自由）。列名は固定ではない。"""
        guess = [
            (self.v_num, ("伝票番号", "伝票no", "伝票№", "納品書")),
            (self.v_maker, ("メーカー", "仕入先", "取引先")),
            (self.v_date, ("日付", "仕入日", "納品日")),
            (self.v_amount, ("金額", "合計")),
        ]
        for var, words in guess:
            var.set("" if var is self.v_num else NONE_CHOICE)
            for h in self.headers:
                if any(w in h.lower() for w in words):
                    var.set(h)
                    break

    def _col_index(self, var):
        v = var.get()
        if not v or v == NONE_CHOICE:
            return None
        return self.headers.index(v)

    # ------------------------------------------------------------------ 実行
    def _start(self):
        folder, excel = self.v_folder.get(), self.v_excel.get()
        if not folder or not Path(folder).is_dir():
            return messagebox.showwarning("入力不足", "伝票フォルダを選んでください。")
        if not excel or not Path(excel).is_file():
            return messagebox.showwarning("入力不足", "仕入一覧表(Excel)を選んでください。")
        if self._col_index(self.v_num) is None:
            return messagebox.showwarning("入力不足", "「伝票番号の列」を選んでください。")
        try:
            if self.v_mock.get():
                reader = MockReader(folder, self.cfg["mock"]["readings_file"])
            else:
                key = get_api_key(self.cfg)
                if not key:
                    return messagebox.showwarning(
                        "APIキー未設定",
                        "AI読み取りにはAPIキーが必要です。環境変数 ANTHROPIC_API_KEY を設定するか、"
                        "config.yaml の api_key_file を指定してください（詳しくはREADME）。\n\n"
                        "動作確認だけなら「テスト用（AIを使わない）」にチェックを入れてください。")
                reader = ClaudeReader(self.cfg, api_key=key)
            cols = ColumnSelection(
                self.v_sheet.get() or None, max(1, int(self.v_header_row.get())),
                self._col_index(self.v_num), self._col_index(self.v_maker),
                self._col_index(self.v_date), self._col_index(self.v_amount))
            n = self.session.load_ledger(excel, cols)
        except Exception as e:
            log.exception("開始前エラー")
            return messagebox.showerror("エラー", f"開始できませんでした。\n{e}")
        log.info("仕入一覧 %d行を読み込み", n)

        self.btn_start.config(state="disabled")
        self.btn_export.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self.progress.config(value=0, maximum=1)
        self.v_status.set(f"仕入一覧 {n}行を読み込みました。伝票を読み取り中…")
        self.cancel_ev.clear()
        self.worker = threading.Thread(target=self._work, args=(folder, reader), daemon=True)
        self.worker.start()

    def _work(self, folder, reader):
        try:
            self.session.read_slips(folder, reader, lambda d, t: self.q.put(("progress", d, t)), self.cancel_ev)
            self.q.put(("done",))
        except Cancelled:
            self.q.put(("cancelled",))
        except Exception as e:   # 1枚ごとの失敗は内側で処理済み。ここに来るのはフォルダが読めない等
            log.exception("処理エラー")
            self.q.put(("error", str(e)))

    def _cancel(self):
        self.cancel_ev.set()
        self.v_status.set("中止しています…")

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    _, d, t = msg
                    self.progress.config(maximum=max(t, 1), value=d)
                    self.v_status.set(f"読み取り中… {d}/{t}枚")
                elif kind == "done":
                    self._finish("照合が完了しました。")
                    self._refresh()
                elif kind == "cancelled":
                    self._finish("中止しました。")
                elif kind == "error":
                    self._finish("エラーが発生しました。")
                    messagebox.showerror("エラー", msg[1])
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _finish(self, text):
        self.btn_start.config(state="normal")
        self.btn_cancel.config(state="disabled")
        self.v_status.set(text)
        if self.session.results:
            self.btn_export.config(state="normal")

    # ------------------------------------------------------------------ 結果一覧
    def _visible(self, r: ResultRow) -> bool:
        f = self.v_filter.get()
        if f == "すべて":
            return True
        if f == "警告あり":
            return bool(r.warnings)
        if f == "未確認のみ":
            return (r.category == REVIEW or bool(r.warnings)) and not r.confirmed
        return r.category == f

    def _refresh(self, keep_row: ResultRow | None = None):
        sel_key = keep_row.key if keep_row else (self._current().key if self._current() else None)
        self.tree.delete(*self.tree.get_children())
        self.shown = [r for r in self.session.results if self._visible(r)]
        pick = None
        for i, r in enumerate(self.shown):
            tags = (r.category, "warn") if (r.warnings and r.category == "一致") else (r.category,)
            mark = "⚠ " if r.warnings else ""
            self.tree.insert("", "end", iid=str(i), tags=tags, values=(
                "✓" if r.confirmed else "", mark + r.label, r.slip_number, r.maker, r.note))
            if r.key == sel_key and pick is None:
                pick = str(i)
        c = summarize(self.session.results)
        warn = sum(1 for r in self.session.results if r.warnings)
        self.v_summary.set("  ".join(f"{k} {v}" for k, v in c.items()) + f"  ⚠警告 {warn}")
        if pick is not None:
            self.tree.selection_set(pick)
            self.tree.see(pick)
        else:
            self._on_select()

    def _current(self) -> ResultRow | None:
        sel = self.tree.selection()
        if sel and int(sel[0]) < len(self.shown):
            return self.shown[int(sel[0])]
        return None

    def _on_click(self, event):
        if self.tree.identify_region(event.x, event.y) == "cell" and self.tree.identify_column(event.x) == "#1":
            iid = self.tree.identify_row(event.y)
            if iid:
                r = self.shown[int(iid)]
                self.session.set_state(r, not r.confirmed, r.memo)
                self.tree.set(iid, "chk", "✓" if r.confirmed else "")
                self.tree.selection_set(iid)
                self._on_select()
                return "break"

    # ------------------------------------------------------------------ 詳細パネル
    def _set_detail_enabled(self, on: bool, can_edit_number: bool = False):
        st = "normal" if on else "disabled"
        self.chk_conf.config(state=st)
        self.ent_memo.config(state=st)
        es = "normal" if (on and can_edit_number) else "disabled"
        for w in (self.ent_manual, self.btn_fix, self.btn_unfix):
            w.config(state=es)

    def _on_select(self):
        r = self._current()
        self._img_cache = None
        if r is None:
            self._set_detail_enabled(False)
            self._text("")
            self._draw_preview()
            return
        self._set_detail_enabled(True, r.is_slip)
        self.v_confirmed.set(r.confirmed)
        self.v_memo.set(r.memo)
        corr = self.session.cache.get_corrections().get(r.key, "") if r.is_slip else ""
        self.v_manual.set(corr or (r.slip_number if r.is_slip and r.category == REVIEW and "/" not in r.slip_number else ""))
        self._text(self._detail_text(r))
        self._draw_preview()

    def _detail_text(self, r: ResultRow) -> str:
        lines = [f"区分: {r.label}"]
        if not r.is_slip:
            lines += ["対応する伝票画像が見つかりませんでした。", f"伝票番号（仕入一覧）: {r.slip_number}", f"備考: {r.note}"]
            return "\n".join(lines)
        sr = self.session.reading_for(r.key)
        lines.append(f"ファイル: {r.source_file}")
        if sr and sr.error:
            lines.append(f"読み取りエラー: {sr.error}")
        elif sr and sr.result:
            x = sr.result
            lines += [
                "AIの読み取り内容" + ("（キャッシュ）" if sr.from_cache else ""),
                f"  伝票番号候補: {' / '.join(x.slip_numbers) or '（読み取れず）'}",
                f"  メーカー: {x.maker or '-'}　日付: {x.date or '-'}　合計: "
                + (f"{x.total_amount:,.0f}円" if x.total_amount is not None else "-"),
                f"  手書き: {'はい' if x.handwritten else 'いいえ'}　自信度: {CONFIDENCE_JA[x.confidence]}",
                f"  メモ: {x.note or '-'}",
            ]
        lines.append(f"判定: {r.note}")
        return "\n".join(lines)

    def _text(self, s: str):
        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", s)
        self.txt.config(state="disabled")

    def _draw_preview(self):
        self.canvas.delete("all")
        r = self._current()
        if r is None or not r.is_slip:
            self.canvas.create_text(10, 10, anchor="nw", fill="white",
                                    text="（伝票画像なし）" if r else "行を選ぶと伝票画像が表示されます")
            return
        sr = self.session.reading_for(r.key)
        if sr is None:
            return
        w, h = max(self.canvas.winfo_width(), 50), max(self.canvas.winfo_height(), 50)
        try:
            if self._img_cache is None or self._img_cache[0] != r.key:
                self._img_cache = (r.key, shrink(render_page(sr.ref, 100), 1600))
            img = self._img_cache[1].copy()
            img.thumbnail((w, h))
            self._photo = ImageTk.PhotoImage(img)
            self.canvas.create_image(w // 2, h // 2, image=self._photo)
        except Exception as e:
            self.canvas.create_text(10, 10, anchor="nw", fill="white", text=f"画像を表示できません: {e}")

    # ------------------------------------------------------------------ 手修正・確認済み
    def _apply_manual(self):
        r = self._current()
        if r is None or not r.is_slip:
            return
        text = self.v_manual.get().strip()
        if not text:
            return messagebox.showinfo("手修正", "伝票番号を入力してください。（修正を消すときは「修正を取り消す」）")
        self._correct(r, text)

    def _clear_manual(self):
        r = self._current()
        if r is not None and r.is_slip:
            self._correct(r, "")

    def _correct(self, r: ResultRow, text: str):
        key = r.key
        self.session.set_correction(key, text)
        new = next((x for x in self.session.results if x.key == key), None)
        self._refresh(keep_row=new)
        c = self.session.results and next((x for x in self.session.results if x.key == key), None)
        if c:
            self.v_status.set(f"再照合しました → {c.label}")

    def _save_state(self):
        r = self._current()
        if r is None:
            return
        self.session.set_state(r, self.v_confirmed.get(), self.v_memo.get())
        for iid, row in enumerate(self.shown):
            if row is r:
                self.tree.set(str(iid), "chk", "✓" if r.confirmed else "")

    # ------------------------------------------------------------------ 出力
    def _export(self):
        path = filedialog.asksaveasfilename(
            title="照合結果の保存先", defaultextension=".xlsx", initialfile=excel_io.default_output_name(date.today()),
            filetypes=[("Excelブック", "*.xlsx")])
        if not path:
            return
        try:
            self._save_state()
            out = self.session.export(path)
        except PermissionError:
            return messagebox.showerror("エラー", "保存できません。同名のファイルをExcelで開いている場合は閉じてください。")
        except Exception as e:
            log.exception("出力エラー")
            return messagebox.showerror("エラー", f"保存できませんでした。\n{e}")
        messagebox.showinfo("出力しました", f"{out}")

    def _about(self):
        messagebox.showinfo("データの取り扱い・設定について",
                            PRIVACY_TEXT + f"\n\n使用モデル: {self.cfg['model']}\n設定ファイル: "
                            f"{self.cfg.get('_config_path') or '（なし・初期値）'}")

    def _on_close(self):
        self.cancel_ev.set()
        self.destroy()


def main():
    try:
        App().mainloop()
    except Exception as e:  # 起動時の設定ミスなど
        logging.getLogger(__name__).exception("起動エラー")
        try:
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("起動エラー", str(e))
        except Exception:
            print(e)


if __name__ == "__main__":
    main()
