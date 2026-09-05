@echo off
chcp 65001 >nul
REM ---- QP-TRACKING: setup moi truong va thu vien ----
REM Tu dong tao virtual environment .venv va cai dat dependencies.

cd /d "%~dp0"

echo.
echo   ========================================
echo       QP-TRACKING - Cai dat moi truong
echo   ========================================
echo.

REM Kiem tra Python trong PATH hoac Python Launcher
set PYTHON_CMD=
where python >nul 2>&1
if not errorlevel 1 (
    set PYTHON_CMD=python
) else (
    where py >nul 2>&1
    if not errorlevel 1 (
        set PYTHON_CMD=py -3
    )
)

if "%PYTHON_CMD%"=="" (
    echo   [!] KHONG TIM THAY PYTHON TREN HE THONG!
    echo.
    echo       1. Vao https://www.python.org/downloads/ tai ban moi nhat.
    echo       2. Khi cai dat, NHO TICH VAO: "Add Python to PATH".
    echo       3. Cai xong, mo lai file setup.bat nay.
    echo.
    pause
    exit /b 1
)

REM Tu dong tao file .env tu .env.example neu chua co
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo   [+] Da khoi tao file .env tu .env.example.
    )
)

REM Tao virtual environment neu chua co
if not exist ".venv\Scripts\python.exe" (
    echo   [*] Dang khoi tao moi truong ao .venv...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo   [!] Khong tao duoc .venv. Kiem tra quyen ghi thu muc.
        pause
        exit /b 1
    )
)

echo   [*] Dang cap nhat pip va cai dat thu vien...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo   [!] Cai dat thu vien that bai. Vui long kiem tra ket noi Internet hoac loi phia tren.
    echo.
    pause
    exit /b 1
)

echo.
echo   ========================================
echo      [OK] Cai dat hoan tat!
echo      Nhanh chong: Bam start.bat de su dung.
echo   ========================================
echo.
pause
