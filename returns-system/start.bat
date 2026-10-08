@echo off
chcp 65001 > nul
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  echo 初回の準備をしています。数分かかります...
  python -m venv .venv || goto :err
  .venv\Scripts\python -m pip install -r requirements.txt || goto :err
)
echo.
echo 起動しました。この黒い画面を閉じるとアプリが止まります。
echo パソコンのブラウザで http://localhost:8000 を開いてください。
.venv\Scripts\python run.py
pause
exit /b
:err
echo.
echo 準備に失敗しました。上に出ている文字を、そのままコピーして伝えてください。
pause
