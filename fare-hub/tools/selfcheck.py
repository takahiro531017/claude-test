"""機密保持セルフチェック。  python -m tools.selfcheck   （問題があれば終了コード1）

  1. 外部通信が無い: ソース/フロントにURL・ネットワーク系importが無い
  2. データがGit管理外: .gitignore が効いており、追跡ファイルに実データ形式が無い
  3. ダミー以外の個人情報らしき文字列（電話番号・郵便番号）が無い
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BAD_IMPORTS = {"requests", "urllib3", "aiohttp", "httpx", "http.client", "urllib.request", "smtplib", "ftplib",
               "telnetlib", "socket", "websockets", "websocket", "paramiko", "boto3", "sentry_sdk", "posthog"}
URL_RE = re.compile(r"https?://(?!(?:localhost|127\.0\.0\.1|\[::1\]|testserver|evil\.example)\b)[^\s\"'<>)]+")
PHONE_RE = re.compile(r"\b0\d{1,4}-\d{1,4}-\d{4}\b|〒\s*\d{3}-?\d{4}")
IGNORE_PATTERNS = ["data/x.sqlite", "uploads/a.pdf", "exports/x.xlsx", "foo.pdf", "foo.db", "data/dummy/x.pdf"]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout


def check_no_network() -> list[str]:
    problems = []
    for p in [*ROOT.glob("app/**/*.py"), ROOT / "run.py"]:  # 実行時コード（tests/tools は除外）
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            mods = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module or ""] if isinstance(n, ast.ImportFrom) else []
            for m in mods:
                if m in BAD_IMPORTS or m.split(".")[0] in BAD_IMPORTS:
                    problems.append(f"{p.relative_to(ROOT)}: network-capable import '{m}'")
    for p in [*ROOT.glob("app/**/*.py"), *ROOT.glob("app/static/*"), ROOT / "run.py", *ROOT.glob("config/*")]:
        for m in URL_RE.finditer(p.read_text(encoding="utf-8")):
            problems.append(f"{p.relative_to(ROOT)}: external URL {m.group(0)[:40]}")
    return problems


def check_git_ignore() -> list[str]:
    problems = []
    for pat in IGNORE_PATTERNS:
        p = ROOT / pat
        if subprocess.run(["git", "check-ignore", "-q", str(p)], cwd=ROOT).returncode != 0:
            problems.append(f"not ignored by git: {pat}")
    for f in _git("ls-files", "-co", "--exclude-standard").splitlines():
        if re.search(r"\.(pdf|sqlite3?|db|xlsx?)$", f, re.I) or re.match(r"(data|uploads|exports)/", f):
            problems.append(f"tracked data-like file: {f}")
    return problems


def check_pii_patterns() -> list[str]:
    problems = []
    for f in _git("ls-files", "-co", "--exclude-standard", ".").splitlines():
        p = ROOT / f
        if p.suffix in {".py", ".md", ".yaml", ".js", ".html", ".txt"} and p.is_file():
            if PHONE_RE.search(p.read_text(encoding="utf-8")):
                problems.append(f"phone/postal-like pattern in {f}")
    return problems


def main() -> int:
    ok = True
    for title, fn in [("外部通信なし", check_no_network), ("Git管理外", check_git_ignore), ("個人情報パターンなし", check_pii_patterns)]:
        probs = fn()
        print(("OK  " if not probs else "NG  ") + title)
        for p in probs:
            print("    -", p)
        ok &= not probs
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
