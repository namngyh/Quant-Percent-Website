@echo off
rem ===================================================================
rem  Dang ky lich chay tu dong cho daily-update.bat.
rem
rem  Chay MOT LAN, bam doi chuot la duoc. KHONG can quyen Administrator.
rem
rem  Lich: 15:15 cac ngay thu 2 den thu 6.
rem  HOSE dong cua phien lien tuc luc 14:45 va het phien ATC khoang
rem  15:00; 15:15 de du bien cho ingestion ghi not bar cuoi.
rem
rem  Go lich:  schtasks /Delete /TN "QuantPercent Daily Update" /F
rem  Xem lich: schtasks /Query /TN "QuantPercent Daily Update" /V /FO LIST
rem  Chay thu: schtasks /Run /TN "QuantPercent Daily Update"
rem ===================================================================

setlocal EnableExtensions

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "TASK=QuantPercent Daily Update"
set "SCRIPT=%ROOT%\daily-update.bat"

echo.
echo ==========================================
echo   DANG KY LICH CAP NHAT TU DONG
echo ==========================================
echo.

if not exist "%SCRIPT%" (
    echo [LOI] Khong thay %SCRIPT%
    pause
    exit /b 1
)

echo Script : %SCRIPT%
echo Lich   : 15:15, thu 2 den thu 6
echo.

rem Khong dung /RL HIGHEST: co do moi la thu doi quyen Administrator, va tac vu
rem nay khong can. No chi goi docker (tai khoan da thuoc nhom docker-users),
rem python va ghi file trong thu muc du an.
rem /F: ghi de neu lich da ton tai, nen chay lai file nay la cap nhat.
schtasks /Create ^
    /TN "%TASK%" ^
    /TR "\"%SCRIPT%\"" ^
    /SC WEEKLY ^
    /D MON,TUE,WED,THU,FRI ^
    /ST 15:15 ^
    /F

if errorlevel 1 (
    echo.
    echo [LOI] Khong dang ky duoc lich.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   XONG
echo.
echo   Moi ngay giao dich luc 15:15, may se tu:
echo     - cap nhat bars_1d
echo     - xuat du lieu moi cho model
echo     - chay MSDP inference
echo     - nap du bao vao database
echo.
echo   Nhat ky: %ROOT%\logs\
echo.
echo   Chay thu ngay:
echo     schtasks /Run /TN "%TASK%"
echo ==========================================
echo.
echo Luu y: may phai dang bat va Docker phai chay vao luc do.
echo        Script tu bo qua cuoi tuan va ngay khong co du lieu.
echo.
pause
endlocal
exit /b 0
