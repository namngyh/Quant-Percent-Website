@echo off
chcp 65001 >nul
REM ---- QP-TRACKING: Khởi động nền tảng ----
REM Nháy đúp file này để chạy. Trình duyệt sẽ tự động được mở.

cd /d "%~dp0"

REM Tự động kiểm tra file .env
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo   [+] Da khoi tao file .env tu .env.example.
    )
)

REM Kiểm tra môi trường ảo .venv, nếu chưa có thì tự động gọi setup.bat
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo   [!] Khong tim thay moi truong ao (.venv).
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
echo       (Dong cua so nay hoac Ctrl+C de tat)
echo   ========================================
echo.

".venv\Scripts\python.exe" run.py

REM Giữ cửa sổ nếu server dừng vì có lỗi
if errorlevel 1 (
    echo.
    echo   [!] Server dung voi loi. Xem thong bao chi tiet phia tren.
    echo.
    pause
)
