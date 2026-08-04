@echo off
rem Chu trinh hang ngay RAEMF-MC: nap data DataPro tu incoming/ -> validate -> chay mo hinh -> bao cao.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [LOI] Khong tim thay .venv\Scripts\python.exe. Hay tao moi truong ao truoc.
    pause
    exit /b 1
)

echo ================================================================
echo  RAEMF-MC - Chay mo hinh hang ngay (%date% %time%)
echo ================================================================
".venv\Scripts\python.exe" -m raemf_mc.cli daily
if errorlevel 1 (
    echo.
    echo [LOI] Chu trinh hang ngay that bai. Xem thong bao phia tren.
) else (
    echo.
    echo [OK] Hoan tat. Bao cao: outputs\current_monitor\report_for_nonspecialists.md
)
pause
