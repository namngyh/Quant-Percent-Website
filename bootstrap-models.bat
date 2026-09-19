@echo off
rem ===================================================================
rem  Quant Percent - chay tang BATCH mot lan cho mot mo hinh.
rem
rem      bootstrap-models.bat rarf-fhe
rem      bootstrap-models.bat dynamic-graph
rem      bootstrap-models.bat msdp
rem      bootstrap-models.bat raemf-mc
rem
rem  Tai sao phai co buoc nay
rem  ------------------------
rem  daily-update.bat chi chay TANG ONLINE: no ap cac phien moi len mot
rem  trang thai da co san va khong train lai gi. Trang thai do phai duoc
rem  sinh ra tu mot lan chay tang batch. Chua co no thi update-latest bao
rem  "Chua co online state" (hoac "Chua co bundle" voi Tempus) roi dung.
rem
rem  Phai chay lai bootstrap cho mo hinh nao vua duoc train lai tang batch:
rem  tang online bi reset theo, va neu bo qua thi update-latest van chay
rem  binh thuong tren state cu MA KHONG BAO LOI. Doi chieu
rem  source_run_metadata trong manifest cua model neu nghi ngo.
rem
rem  Nhan tung mo hinh mot, co y: chi phi rat khac nhau va khong nen chay
rem  ca bon trong mot lan.
rem    rarf-fhe       vai phut
rem    dynamic-graph  nang, hang chuc phut
rem    msdp           nhanh, chi seed state tu bundle production co san
rem    raemf-mc       fit ton HANG GIO va can venv co torch CUDA
rem
rem  KHONG sua code trong luc dynamic-graph dang chay run-all:
rem  validate_publication_state so code fingerprint va se tu choi publish o
rem  cuoi, lam mat toan bo thoi gian chay.
rem
rem  Ghi chu: khong dung dau tieng Viet vi cmd hay bi vo font.
rem ===================================================================

setlocal EnableExtensions

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

if not defined QP_MODEL_PYTHON set "QP_MODEL_PYTHON=python"
set "PY_MODEL=%QP_MODEL_PYTHON%"

rem Stdout da redirect mac dinh la cp1252 tren Windows, con thong bao cua ca
rem bon model deu co dau tieng Viet. Khong ep UTF-8 thi moi dong log co dau
rem se nem UnicodeEncodeError ngay ben trong handler: chuong trinh van chay
rem nhung in ra mot traceback day du moi lan, du de chon vui log that.
set "PYTHONIOENCODING=utf-8"

set "TARGET=%~1"
if "%TARGET%"=="" goto :usage

"%PY_MODEL%" -c "import psycopg, pandas" >nul 2>&1
if errorlevel 1 (
    echo [LOI] Python cho model ^(%PY_MODEL%^) thieu psycopg hoac pandas.
    echo       Dat QP_MODEL_PYTHON tro sang ban co du roi chay lai.
    goto :fail
)

if /i "%TARGET%"=="rarf-fhe"      goto :rarf
if /i "%TARGET%"=="dynamic-graph" goto :dg
if /i "%TARGET%"=="msdp"          goto :msdp
if /i "%TARGET%"=="raemf-mc"      goto :raemf
echo [LOI] Khong biet mo hinh "%TARGET%".
goto :usage

rem -------------------------------------------------------------------
:rarf
echo === RARF-FHE: sync-source, run-all, init-online-state ===
pushd "%ROOT%\models\rarf-fhe"
set "PYTHONPATH=%ROOT%\models\rarf-fhe\src"
"%PY_MODEL%" -m vnindex_model.cli sync-source --config configs/default.yaml       || goto :step_failed
"%PY_MODEL%" -m vnindex_model.cli run-all --config configs/default.yaml           || goto :step_failed
"%PY_MODEL%" -m vnindex_model.cli init-online-state --config configs/default.yaml || goto :step_failed
goto :ok

rem -------------------------------------------------------------------
:dg
rem Dung local.yaml, khong dung fast.yaml: fast.yaml tu ghi trong artifact
rem rang no "NOT publication grade", va mot lan chay fast se de len 73 file
rem trong artifacts\ - ke ca hinh va bao cao - ma nhin giao dien khong thay.
echo === DynamicGraph: run-all, init-online-state (nang, hang chuc phut) ===
pushd "%ROOT%\models\dynamic-graph"
set "PYTHONPATH=%ROOT%\models\dynamic-graph\src"
"%PY_MODEL%" -m dynamicgraph.cli run-all --config config/local.yaml            || goto :step_failed
"%PY_MODEL%" -m dynamicgraph.cli init-online-state --config config/local.yaml  || goto :step_failed
goto :ok

rem -------------------------------------------------------------------
:msdp
rem Khong train lai: chi seed state tu bundle production da co
rem (artifacts\models\production_ensemble_manifest.json).
echo === MSDP: sync_source, init_online_state ===
pushd "%ROOT%\models\msdp"
"%PY_MODEL%" scripts\sync_source.py --config configs/default.yaml >nul || goto :step_failed
"%PY_MODEL%" scripts\init_online_state.py --data data\raw\VNINDEX_Daily_db.csv --model artifacts\models\production_ensemble_manifest.json || goto :step_failed
goto :ok

rem -------------------------------------------------------------------
:raemf
rem fit can torch CUDA va ton hang gio. Python he thong chi co torch CPU,
rem du de chay `predict` hang ngay nhung khong du de fit trong thoi gian
rem chap nhan duoc, nen buoc nay doi bien QP_RAEMF_PYTHON tro vao mot venv
rem co CUDA thay vi chay nham bang CPU roi treo may ca dem.
echo === Tempus / RAEMF-VB-MC: fit (HANG GIO, can venv CUDA) ===
if not defined QP_RAEMF_PYTHON (
    echo [LOI] Chua dat QP_RAEMF_PYTHON.
    echo       fit can torch CUDA; Python he thong chi co torch CPU.
    echo       Vi du: set QP_RAEMF_PYTHON=C:\duong\dan\.venv\Scripts\python.exe
    goto :fail
)
pushd "%ROOT%\models\raemf-mc"
set "PYTHONPATH=%ROOT%\models\raemf-mc\src"
"%QP_RAEMF_PYTHON%" -m raemf_mc.cli fit --config configs\gpu_research.yaml || goto :step_failed
goto :ok

rem -------------------------------------------------------------------
:ok
set "PYTHONPATH="
popd
echo.
echo XONG. Gio daily-update.bat co the cap nhat "%TARGET%" moi phien.
endlocal
exit /b 0

:step_failed
set "PYTHONPATH="
popd
echo.
echo [LOI] Mot buoc that bai - xem thong bao ben tren. Trang thai online
echo       cua "%TARGET%" chua duoc tao, daily-update.bat se van bao loi.
endlocal
exit /b 1

:usage
echo.
echo   bootstrap-models.bat ^<rarf-fhe^|dynamic-graph^|msdp^|raemf-mc^>
echo.
echo   Chay tang batch mot lan de tao trang thai cho tang online.
echo   Chay lai sau moi lan train lai tang batch cua mo hinh do.
echo.
:fail
endlocal
exit /b 1
