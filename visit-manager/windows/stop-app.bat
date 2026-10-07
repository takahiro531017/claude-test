@echo off
chcp 932 >nul
echo 営業訪問管理アプリを停止します...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"
echo 停止しました。(動いていなかった場合もこの表示になります)
pause
