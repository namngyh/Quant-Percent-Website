@echo off
rem ===================================================================
rem  Quant Percent - cap nhat sau khi dong phien.
rem
rem  Chay tay:  daily-update.bat
rem  Chay tu dong: xem install-schedule.bat (dang ky Task Scheduler)
rem
rem  Trinh tu, dung thu tu phu thuoc:
rem    1. backfill.py daily  -> bars_1d cho bieu do lich su
rem    2. export CSV tu DB   -> du lieu dau vao cho model
rem    3. MSDP inference     -> du bao moi (~1 giay, khong train lai)
rem    4. load vao quant.*   -> website doc duoc
rem
rem  Tu bo qua neu hom nay khong phai ngay giao dich: thu 7, chu nhat,
rem  hoac khong co bar moi trong database.
rem  Ghi nhat ky vao logs\daily-update-YYYY-MM-DD.log
rem  Ghi chu: khong dung dau tieng Viet vi cmd hay bi vo font.
rem ===================================================================

setlocal EnableExtensions EnableDelayedExpansion

goto :after_helpers
:sleep
set /a "_s=%~1+1"
ping -n %_s% 127.0.0.1 >nul 2>&1
exit /b 0
:after_helpers

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "DBDIR=D:\Database - QuantPercent"
set "PY_BE=%ROOT%\backend\.venv\Scripts\python.exe"
set "PY_MSDP=C:\qpvenv\msdp\Scripts\python.exe"
rem Cac script trong database\scripts doc chuoi ket noi tu PG_DSN. Mat khau
rem khong nam trong ma nguon nua, nen phai dat bien nay truoc khi chay.
rem Dat bien he thong (setx PG_DSN "...") de khong luu mat khau vao file nay.
if not defined PG_DSN (
    call :fail "Chua dat PG_DSN. Chay: setx PG_DSN \"postgresql://quant:<matkhau>@localhost:5432/market\""
    goto :done
)

set "LOGDIR=%ROOT%\logs"
set "ARTIFACTS=%ROOT%\artifacts"

if not exist "%LOGDIR%" mkdir "%LOGDIR%"
if not exist "%ARTIFACTS%" mkdir "%ARTIFACTS%"

rem Ngay dang ISO, doc tu PowerShell de khong phu thuoc dinh dang vung.
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%d"
set "LOG=%LOGDIR%\daily-update-%TODAY%.log"

call :log "=============================================="
call :log "Bat dau cap nhat: %TODAY%"

rem --- Bo qua cuoi tuan --------------------------------------------
for /f %%w in ('powershell -NoProfile -Command "[int](Get-Date).DayOfWeek"') do set "DOW=%%w"
if "%DOW%"=="0" call :log "Chu nhat - bo qua." & goto :done
if "%DOW%"=="6" call :log "Thu bay - bo qua." & goto :done

rem --- Kiem tra dieu kien ------------------------------------------
if not exist "%PY_BE%" call :fail "Thieu moi truong Python backend: %PY_BE%" & goto :done
if not exist "%PY_MSDP%" call :fail "Thieu moi truong MSDP: %PY_MSDP%" & goto :done

docker info >nul 2>&1
if errorlevel 1 call :fail "Docker chua chay - khong cap nhat duoc." & goto :done

rem --- Co du lieu moi cho hom nay khong? ----------------------------
rem Ingestion chi ghi bar khi thi truong mo. Khong co bar hom nay nghia
rem la ngay nghi le hoac may thu thap khong chay; dung lai thay vi chay
rem model tren du lieu cu roi ghi de du bao dang dung.
rem Dem qua PG_DSN, dung database ma cac buoc sau se ghi vao. Truoc day
rem dong nay goi "docker exec qp-timescaledb" - container local, gan cung -
rem nen khi ingestion chuyen sang VPS thi cong gac dem mot database khong ai
rem ghi vao nua, va job bo qua moi ngay ma van tra ve exit code 0.
set "HASBAR="
for /f "usebackq delims=" %%v in (`""%PY_BE%" "%ROOT%\database\scripts\has_bars_today.py""`) do set "HASBAR=%%v"
if not defined HASBAR call :fail "Khong doc duoc database." & goto :done
if "%HASBAR%"=="0" call :log "Khong co bar nao hom nay - co the la ngay nghi. Bo qua." & goto :done
call :log "Co %HASBAR% bar phut hom nay - tiep tuc."

rem --- 1. bars_1d --------------------------------------------------
call :log "[1/4] Cap nhat bars_1d (backfill daily)..."
pushd "%DBDIR%"
docker compose stop ingestion >>"%LOG%" 2>&1
docker compose run --rm --no-deps ingestion python backfill.py daily >>"%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
docker compose start ingestion >>"%LOG%" 2>&1
popd
if not "%RC%"=="0" call :log "  [CANH BAO] backfill loi (ma %RC%) - van tiep tuc."

rem --- 2. CSV dau vao cho model ------------------------------------
call :log "[2/4] Xuat VNINDEX_Daily.csv tu database..."
"%PY_BE%" "%ROOT%\database\scripts\export_vnindex_daily.py" --repo-root "%ROOT%" >>"%LOG%" 2>&1
if errorlevel 1 call :fail "Xuat CSV that bai." & goto :done

rem --- 3. MSDP inference -------------------------------------------
call :log "[3/4] Chay MSDP inference..."
"%PY_MSDP%" "%ROOT%\database\scripts\run_msdp_inference.py" --model-root "%ROOT%\models\msdp" --out "%ARTIFACTS%\msdp_latest.json" >>"%LOG%" 2>&1
if errorlevel 1 call :fail "MSDP inference that bai." & goto :done

rem --- 4. Nap vao schema quant -------------------------------------
call :log "[4/4] Nap ket qua vao database..."
"%PY_BE%" "%ROOT%\database\scripts\load_model_outputs.py" --msdp "%ARTIFACTS%\msdp_latest.json" >>"%LOG%" 2>&1
if errorlevel 1 call :fail "Nap ket qua that bai." & goto :done

call :log "HOAN TAT - website da co du bao moi."

:done
call :log "Ket thuc."
endlocal
exit /b 0

:log
echo %~1
echo [%date% %time%] %~1 >>"%LOG%"
exit /b 0

:fail
echo [LOI] %~1
echo [%date% %time%] [LOI] %~1 >>"%LOG%"
exit /b 0
