@echo off
rem ===================================================================
rem  Quant Percent - cap nhat sau khi dong phien.
rem
rem  Chay tay:  daily-update.bat
rem  Chay tu dong: xem install-schedule.bat (dang ky Task Scheduler)
rem
rem  Trinh tu, dung thu tu phu thuoc:
rem    1. backfill.py daily  -> bars_1d cho bieu do lich su VA cho ca 4 model
rem    2. RARF-FHE           -> sync-source roi update-latest
rem    3. MSDP               -> sync_source roi update_latest
rem    4. DynamicGraph       -> update-latest (doc thang DB, khong qua file)
rem    5. Tempus / RAEMF     -> predict tu bundle da fit
rem    6. Nap vao quant.* va dong bo file mang luoi cho website
rem
rem  Bon mo hinh DOC LAP nhau: khac stack, khac artifact, khong dung chung
rem  dong code nao. Mot mo hinh hong KHONG duoc chan ba cai con lai, nen moi
rem  buoc tu bat loi rieng, va buoc [6] danh dau mo hinh hong bang
rem  --mark-failed thay vi de dong cu cua no nam lai trong quant.model_runs
rem  trong nhu vua chay thanh cong.
rem
rem  Moi model tu lay du lieu tu bars_1d qua DSN rieng trong .env cua no, nen
rem  o day khong con buoc xuat VNINDEX_Daily.csv nua: cai do la giai phap tam
rem  hoi ba model con doc file tinh nam san trong repo.
rem
rem  Tang online KHONG train lai gi. Truoc lan chay dau tien, va sau MOI lan
rem  chay lai tang batch, phai chay bootstrap-models.bat cho mo hinh do -
rem  neu khong, buoc update-latest bao "Chua co online state" va dung lai.
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

rem Cac model doc bars_1d bang psycopg va chay torch/sklearn/hmmlearn. Chi
rem Python he thong co du bo do: cac venv cu (C:\qpvenv\*, va .venv trong
rem tung repo) deu THIEU psycopg nen khong chay duoc tang online. Dat bien
rem QP_MODEL_PYTHON de tro sang trinh thong dich khac neu can.
if not defined QP_MODEL_PYTHON set "QP_MODEL_PYTHON=python"
set "PY_MODEL=%QP_MODEL_PYTHON%"

rem Stdout da redirect mac dinh la cp1252 tren Windows, con thong bao cua ca
rem bon model deu co dau tieng Viet. Khong ep UTF-8 thi moi dong log co dau
rem se nem UnicodeEncodeError ngay ben trong handler: chuong trinh van chay
rem nhung in ra mot traceback day du moi lan, du de chon vui log that.
set "PYTHONIOENCODING=utf-8"

rem Cac script trong database\scripts doc chuoi ket noi tu PG_DSN. Mat khau
rem khong nam trong ma nguon nua, nen phai dat bien nay truoc khi chay.
rem Dat bien he thong (setx PG_DSN "...") de khong luu mat khau vao file nay.
if not defined PG_DSN (
    call :fail "Chua dat PG_DSN. Chay: setx PG_DSN \"postgresql://quant:<matkhau>@10.10.0.1:5432/market\""
    goto :done
)

set "LOGDIR=%ROOT%\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

rem Ngay dang ISO, doc tu PowerShell de khong phu thuoc dinh dang vung.
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%d"
set "LOG=%LOGDIR%\daily-update-%TODAY%.log"

rem Ket qua tung mo hinh. 0 = chua chay hoac hong, 1 = xong.
set "OK_RARF=0"
set "OK_MSDP=0"
set "OK_DG=0"
set "OK_TEMPUS=0"

call :log "=============================================="
call :log "Bat dau cap nhat: %TODAY%"

rem --- Bo qua cuoi tuan --------------------------------------------
for /f %%w in ('powershell -NoProfile -Command "[int](Get-Date).DayOfWeek"') do set "DOW=%%w"
if "%DOW%"=="0" call :log "Chu nhat - bo qua." & goto :done
if "%DOW%"=="6" call :log "Thu bay - bo qua." & goto :done

rem --- Kiem tra dieu kien ------------------------------------------
if not exist "%PY_BE%" call :fail "Thieu moi truong Python backend: %PY_BE%" & goto :done

rem Kiem tra som, mot lan, thay vi de bon mo hinh lan luot bao cung mot loi.
"%PY_MODEL%" -c "import psycopg, pandas" >nul 2>&1
if errorlevel 1 (
    call :fail "Python cho model (%PY_MODEL%) thieu psycopg hoac pandas."
    call :log  "  Cai vao Python he thong, hoac dat QP_MODEL_PYTHON tro sang ban co du."
    goto :done
)

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
rem Ca bon mo hinh doc bars_1d, nen buoc nay phai xong truoc tat ca.
call :log "[1/6] Cap nhat bars_1d (backfill daily)..."
pushd "%DBDIR%"
docker compose stop ingestion >>"%LOG%" 2>&1
docker compose run --rm --no-deps ingestion python backfill.py daily >>"%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
docker compose start ingestion >>"%LOG%" 2>&1
popd
if not "%RC%"=="0" call :log "  [CANH BAO] backfill loi (ma %RC%) - van tiep tuc."

rem --- 2. RARF-FHE -------------------------------------------------
rem sync-source chup snapshot tu DB ra file de tang batch van hash mot file
rem nhu cu; update-latest ap cac phien moi len online state, khong refit.
call :log "[2/6] RARF-FHE..."
pushd "%ROOT%\models\rarf-fhe"
set "PYTHONPATH=%ROOT%\models\rarf-fhe\src"
"%PY_MODEL%" -m vnindex_model.cli sync-source --config configs/default.yaml >>"%LOG%" 2>&1
if errorlevel 1 (
    call :log "  [LOI] sync-source that bai."
) else (
    "%PY_MODEL%" -m vnindex_model.cli update-latest --config configs/default.yaml >>"%LOG%" 2>&1
    if errorlevel 1 (call :log "  [LOI] update-latest that bai.") else (set "OK_RARF=1")
)
set "PYTHONPATH="
popd
if "%OK_RARF%"=="1" call :log "  OK"

rem --- 3. MSDP -----------------------------------------------------
rem Cham diem cac du bao da dao han, gop vao posterior cua cong Hedge, roi
rem suy luan lai. Khong train lai gi, chay khoang 1 giay.
call :log "[3/6] MSDP..."
pushd "%ROOT%\models\msdp"
"%PY_MODEL%" scripts\sync_source.py --config configs/default.yaml >>"%LOG%" 2>&1
if errorlevel 1 (
    call :log "  [LOI] sync_source that bai."
) else (
    "%PY_MODEL%" scripts\update_latest.py --data data/raw/VNINDEX_Daily_db.csv --model artifacts/models/production_ensemble_manifest.json >>"%LOG%" 2>&1
    if errorlevel 1 (call :log "  [LOI] update_latest that bai.") else (set "OK_MSDP=1")
)
popd
if "%OK_MSDP%"=="1" call :log "  OK"

rem --- 4. DynamicGraph ---------------------------------------------
rem Khong co buoc sync: connector Postgres doc thang, khong qua file trung
rem gian. update-latest ghi lai artifacts\latest\ bang dung ham publish cua
rem tang batch, nen khong con phai goi export-website rieng nua.
call :log "[4/6] DynamicGraph..."
pushd "%ROOT%\models\dynamic-graph"
set "PYTHONPATH=%ROOT%\models\dynamic-graph\src"
"%PY_MODEL%" -m dynamicgraph.cli update-latest --config config/local.yaml >>"%LOG%" 2>&1
if errorlevel 1 (call :log "  [LOI] update-latest that bai.") else (set "OK_DG=1")
set "PYTHONPATH="
popd
if "%OK_DG%"=="1" call :log "  OK"

rem --- 5. Tempus / RAEMF-VB-MC -------------------------------------
rem predict nap lai bundle da fit va chi chay bo loc tien len; fit ton hang
rem gio va KHONG chay o day.
call :log "[5/6] Tempus (RAEMF-VB-MC)..."
pushd "%ROOT%\models\raemf-mc"
set "PYTHONPATH=%ROOT%\models\raemf-mc\src"
"%PY_MODEL%" -m raemf_mc.cli predict --source database >>"%LOG%" 2>&1
if errorlevel 1 (call :log "  [LOI] predict that bai.") else (set "OK_TEMPUS=1")
set "PYTHONPATH="
popd
if "%OK_TEMPUS%"=="1" call :log "  OK"

rem --- 6. Nap ket qua ----------------------------------------------
rem Duong dan tuong doi, chay tu %ROOT%: tranh phai long dau nhay trong bien
rem khi ghep tham so.
call :log "[6/6] Nap ket qua vao database..."
pushd "%ROOT%"

set "LOADARGS="
if "%OK_MSDP%"=="1" set "LOADARGS=%LOADARGS% --msdp models\msdp\artifacts\predictions\latest_forecast.json"
if not "%OK_MSDP%"=="1" set "LOADARGS=%LOADARGS% --mark-failed msdp"
if "%OK_RARF%"=="1" set "LOADARGS=%LOADARGS% --rarf-forecast models\rarf-fhe\artifacts\forecasts\latest_forecast_summary.json"
if not "%OK_RARF%"=="1" set "LOADARGS=%LOADARGS% --mark-failed rarf-fhe"
if "%OK_TEMPUS%"=="1" set "LOADARGS=%LOADARGS% --raemf models\raemf-mc\artifacts\forecasts\latest_forecast.json"
if not "%OK_TEMPUS%"=="1" set "LOADARGS=%LOADARGS% --mark-failed raemf-mc"
if "%OK_DG%"=="1" set "LOADARGS=%LOADARGS% --dynamic-graph models\dynamic-graph\artifacts\latest\latest_dynamicgraph.json"
if not "%OK_DG%"=="1" set "LOADARGS=%LOADARGS% --mark-failed dynamic-graph"

"%PY_BE%" database\scripts\load_model_outputs.py%LOADARGS% >>"%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
popd
if not "%RC%"=="0" call :fail "Nap ket qua that bai (ma %RC%)."

rem Bang xep hang VN30 tren trang /models/dynamic-graph doc file tinh trong
rem frontend\public\research\, khong doc database. Khong co buoc chep nay thi
rem model chay moi ngay ma trang van hien so cua lan chay truoc.
rem Luu y: buoc nay chi cap nhat ban local; muon len site that thi van phai
rem commit hai file do roi trien khai lai.
if "%OK_DG%"=="1" (
    call :log "      Dong bo file mang luoi sang website..."
    pushd "%ROOT%\frontend"
    call npm run research:sync >>"%LOG%" 2>&1
    if errorlevel 1 call :log "      [CANH BAO] research:sync loi - trang van dung file cu."
    popd
)

call :log "----------------------------------------------"
set "FAILED="
if "%OK_RARF%"=="1" (call :log "  rarf-fhe       OK") else (call :log "  rarf-fhe       LOI" & set "FAILED=1")
if "%OK_MSDP%"=="1" (call :log "  msdp           OK") else (call :log "  msdp           LOI" & set "FAILED=1")
if "%OK_DG%"=="1" (call :log "  dynamic-graph  OK") else (call :log "  dynamic-graph  LOI" & set "FAILED=1")
if "%OK_TEMPUS%"=="1" (call :log "  raemf-mc       OK") else (call :log "  raemf-mc       LOI" & set "FAILED=1")

if defined FAILED (
    call :log "Mot so mo hinh chua chay duoc. Neu bao 'Chua co online state' hoac"
    call :log "'Chua co bundle', chay bootstrap-models.bat cho mo hinh do mot lan."
) else (
    call :log "HOAN TAT - website da co du bao moi."
)

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
