@echo off
chcp 65001 >nul
REM ---- QP-TRACKING: start the platform ----
REM Double-click this file to run. It opens your browser automatically.

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo   [!] Khong tim thay .venv - chay setup.bat truoc.
    echo.
    pause
    exit /b 1
)

echo.
echo   QP-TRACKING dang khoi dong...
echo   Dong cua so nay ^(hoac Ctrl+C^) de tat.
echo.

".venv\Scripts\python.exe" run.py

REM Keep the window open if the server exited because of an error.
if errorlevel 1 (
    echo.
    echo   [!] Server dung voi loi. Xem thong bao phia tren.
    pause
)
