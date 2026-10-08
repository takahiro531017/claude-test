"""起動: python run.py   (社内LANの他の端末からも接続できるよう 0.0.0.0 で待ち受けます)"""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=os.environ.get("RETURNS_HOST", "0.0.0.0"),
                port=int(os.environ.get("RETURNS_PORT", "8000")))
