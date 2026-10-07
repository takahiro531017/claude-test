@echo off
chcp 932 >nul
echo ===== このパソコンのIPアドレス =====
ipconfig | findstr /C:"IPv4"
echo.
echo 他のパソコンやスマホのブラウザで、次のように入力して開きます。
echo    http://(上のIPv4アドレス):8000/
echo 例: IPv4アドレスが 192.168.1.20 なら http://192.168.1.20:8000/
echo.
pause
