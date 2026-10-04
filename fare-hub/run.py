"""起動: python run.py [--port 8765]   ※ 127.0.0.1 固定（外部公開しない）"""
import argparse
import logging

import uvicorn

from app.main import create_app

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    print(f"fare-hub: http://127.0.0.1:{args.port}  (localhostのみ)")
    # access_log 無効: URL（検索語）をログに残さない
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port, access_log=False, log_level="warning")
