@echo off
rem 単一exeを作る（Windows）。事前に: pip install -r requirements-dev.txt
chcp 65001 >nul
pyinstaller --onefile --noconsole --name ShiireCheck --collect-all pymupdf run_app.py
if errorlevel 1 goto :eof
copy /Y config.yaml dist\config.yaml
echo.
echo 完成: dist\ShiireCheck.exe  （config.yaml を同じフォルダに置いて配布してください）
