@echo off
chcp 65001 >nul
REM ---- QP-TRACKING: one-time setup ----
REM Creates the virtual environment and installs dependencies.

cd /d "%~dp0"

where python >/dev/null 2>&1
if errorlevel 1 (
    echo.
    echo   [!] Khong tim thay Python. Cai tu https://python.org roi chay lai.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo   Dang tao moi truong ao...
    python -m venv .venv
)

echo   Dang cai thu vien ^(mat vai phut lan dau^)...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo   [!] Cai dat that bai.
    pause
    exit /b 1
)

echo.
echo   Xong. Gio chay start.bat de mo nen tang.
echo.
pause
