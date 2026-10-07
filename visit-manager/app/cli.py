"""運用用CLI: python -m app.cli <command>"""
import argparse
import shutil
import sqlite3
import sys

from . import auth, config, db, importer


def main():
    ap = argparse.ArgumentParser(prog="app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("import-master", help="マスタxlsxを取り込む")
    p.add_argument("path")
    p = sub.add_parser("reset-password", help="ユーザーの一時パスワードを再発行")
    p.add_argument("user_id")
    p = sub.add_parser("backup", help="DBをバックアップ")
    p.add_argument("dest")
    a = ap.parse_args()
    conn = db.connect()
    db.init_db(conn)
    if a.cmd == "import-master":
        r = importer.import_master(conn, a.path, a.path.split("/")[-1], "cli")
        users = r.pop("new_users")
        print({k: v for k, v in r.items() if not isinstance(v, list)})
        print(f"重複: {len(r['duplicates'])}件 / エラー行: {len(r['errors'])}件 / 警告: {len(r['warnings'])}件")
        for u in users:
            print(f"新規ユーザー ID={u['id']} {u['name']} 一時パスワード={u['temp_password']}")
    elif a.cmd == "reset-password":
        if not conn.execute("SELECT 1 FROM users WHERE id=?", (a.user_id,)).fetchone():
            sys.exit("ユーザーが見つかりません")
        pw = auth.temp_password()
        conn.execute("UPDATE users SET password_hash=?, must_change=1 WHERE id=?", (auth.hash_password(pw), a.user_id))
        conn.commit()
        auth.drop_session(conn, None, a.user_id)
        print(f"一時パスワード: {pw}")
    elif a.cmd == "backup":
        dst = sqlite3.connect(a.dest)
        conn.backup(dst)  # 稼働中でも整合したコピーが取れる
        dst.close()
        print("バックアップ完了:", a.dest)


if __name__ == "__main__":
    main()
