"""GUIの通し確認（Tkinterと表示環境がある場合のみ。Linuxでは xvfb-run pytest で実行）。"""
import os

import pytest

tk = pytest.importorskip("tkinter")
if os.name != "nt" and not os.environ.get("DISPLAY"):
    pytest.skip("表示環境がありません", allow_module_level=True)


def test_gui_flow(cfg, dummy, tmp_path, monkeypatch):
    from tkinter import messagebox

    from shiire_check import excel_io
    from shiire_check.cache import Cache
    from shiire_check.gui import App
    from shiire_check.service import CheckSession

    cfg = dict(cfg, data_dir=str(tmp_path))
    monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(messagebox, "showwarning", lambda *a, **k: (_ for _ in ()).throw(AssertionError(a)))
    monkeypatch.setattr(messagebox, "showerror", lambda *a, **k: (_ for _ in ()).throw(AssertionError(a)))
    app = App(cfg)
    try:
        app.v_folder.set(str(dummy["slips"]))
        app.v_excel.set(str(dummy["ledger"]))
        app.cb_sheet["values"] = excel_io.list_sheets(dummy["ledger"])
        app.v_sheet.set("仕入一覧")
        app._load_headers()
        assert app.v_num.get() == "C列: 伝票番号" and app.v_amount.get() == "D列: 金額"   # 見出しから仮選択
        app.v_mock.set(True)
        app._start()
        for _ in range(300):            # 別スレッドの完了待ち（GUIは固まらず更新される）
            app.update()
            if str(app.btn_start["state"]) == "normal" and app.session.results:
                break
            app.after(20)
            import time; time.sleep(0.02)
        assert len(app.tree.get_children()) == len(app.session.results) > 10
        # 「要確認」で絞り込み
        app.v_filter.set("要確認")
        app._refresh()
        assert all("要確認" in app.tree.item(i, "values")[1] for i in app.tree.get_children())
        # ぼやけ伝票を選択 → 手修正 → 再照合で「一致」
        target = next(i for i, r in enumerate(app.shown) if r.source_file == "三光産業_ぼやけ.jpg")
        app.tree.selection_set(str(target))
        app.update()
        app.v_manual.set("sk-3319")
        app._apply_manual()
        app.update()
        row = next(r for r in app.session.results if r.source_file == "三光産業_ぼやけ.jpg")
        assert row.category == "一致"
        assert all(r.source_file != "三光産業_ぼやけ.jpg" for r in app.shown)   # 絞り込みから消える
        # 確認済み
        app.tree.selection_set("0")
        app.update()
        app.v_confirmed.set(True)
        app._save_state()
        assert app.shown[0].confirmed
    finally:
        app.destroy()
