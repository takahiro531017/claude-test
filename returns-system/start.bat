@echo off
cd /d "%~dp0"
echo === Returns system ===
if exist ".venv\Scripts\python.exe" goto run
echo First-time setup. Please wait a few minutes...
python -m venv .venv
if errorlevel 1 goto err
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto err
:run
echo.
echo Started. Do NOT close this window.
echo Open http://localhost:8000 in your browser.
echo.
".venv\Scripts\python.exe" run.py
echo.
echo The app has stopped. Please read the messages above.
pause
exit /b
:err
echo.
echo Setup FAILED. Please copy the messages above and send them to me.
pause
