@echo off
chcp 932 >nul
echo パソコンを起動してログインしたときに、アプリが自動で起動するように設定します。
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup')+'\VisitManager.lnk'); $s.TargetPath='wscript.exe'; $s.Arguments='%~dp0start-app.vbs silent'; $s.WorkingDirectory='%~dp0'; $s.Save()"
echo 設定しました。次回からパソコンにログインすると、アプリが自動で起動します。
pause
