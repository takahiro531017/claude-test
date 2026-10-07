@echo off
chcp 932 >nul
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo 管理者の権限で、もう一度開き直します。確認が出たら「はい」を押してください。
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
echo 社内ネットワークの他の端末から、アプリ(8000番)に接続できるようにします。
netsh advfirewall firewall delete rule name="VisitManager" >nul 2>&1
netsh advfirewall firewall add rule name="VisitManager" dir=in action=allow protocol=TCP localport=8000 profile=private,domain remoteip=localsubnet
echo.
echo 完了しました。(同じ社内ネットワークの端末だけが対象です)
pause
