@echo off
chcp 65001 >nul
REM ---- QP-TRACKING: Khoi dong nen tang ----
REM Nhay dup file nay de chay. Trinh duyet se tu dong duoc mo.

cd /d "%~dp0"

REM Tu dong kiem tra file .env
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo   [+] Da khoi tao file .env tu .env.example.
    )
)

REM Kiem tra moi truong ao .venv
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo   [!] Khong tim thay moi truong ao .venv.
    echo   [*] He thong se tu dong chay setup.bat de cai dat...
    echo.
    call setup.bat
    if not exist ".venv\Scripts\python.exe" (
        echo.
        echo   [!] Khong the khoi dong do thieu .venv.
        pause
        exit /b 1
    )
)

echo.
echo   ========================================
echo       QP-TRACKING DANG KHOI DONG...
echo       Trinh duyet se tu dong mo.
echo       Dong cua so nay hoac Ctrl+C de tat.
echo   ========================================
echo.

".venv\Scripts\python.exe" run.py

echo.
echo   ========================================
echo       Server da dung.
echo   ========================================
echo.
pause
