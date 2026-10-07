@echo off
chcp 932 >nul
powershell -NoProfile -Command "Remove-Item ([Environment]::GetFolderPath('Startup')+'\VisitManager.lnk') -ErrorAction SilentlyContinue"
echo ©“®‹N“®‚Ìİ’è‚ğ‰ğœ‚µ‚Ü‚µ‚½B
pause
