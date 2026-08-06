@echo off
rem ===================================================================
rem  Quant Percent - khoi dong toan bo stack bang mot lenh.
rem
rem  Chay:  start.bat          (hoac bam doi chuot vao file nay)
rem
rem  Script tu lam:
rem    1. Bat Docker Desktop neu chua chay, doi den khi san sang
rem    2. Bat DataPro.Client neu chua chay
rem    3. Bat 3 container database neu chua len
rem    4. Mo 2 cua so: backend (8000) va website (3000)
rem    5. Mo trinh duyet khi website san sang
rem
rem  Tat: dong 2 cua so do, hoac Ctrl+C trong tung cua so.
rem       Database van chay nen (dung tat neu con dung).
rem  Ghi chu: khong dung dau tieng Viet vi cmd hay bi vo font.
rem ===================================================================

setlocal EnableExtensions

rem "timeout" bao loi "Input redirection is not supported" khi script duoc
rem goi ma stdin khong phai console (vi du chay tu mot cong cu khac), va khi
rem do no thoat ngay nen moi vong cho deu mat tac dung. "ping" doi duoc trong
rem moi truong hop nen dung lam ham ngu: goi :sleep <so giay>.
goto :after_helpers

:sleep
set /a "_s=%~1+1"
ping -n %_s% 127.0.0.1 >nul 2>&1
exit /b 0

:after_helpers

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "BACKEND=%ROOT%\backend"
set "FRONTEND=%ROOT%\frontend"
set "DBDIR=D:\Database - QuantPercent"
set "DOCKER_EXE=C:\Program Files\Docker\Docker\Docker Desktop.exe"
set "DATAPRO_EXE=C:\Program Files\DataPro\DataPro.Client.exe"

title Quant Percent - khoi dong

echo.
echo ==========================================
echo   QUANT PERCENT - KHOI DONG
echo ==========================================
echo.

rem --- Kiem tra da cai dat chua -------------------------------------
if not exist "%BACKEND%\.venv\Scripts\python.exe" (
    echo [LOI] Chua co moi truong Python cua backend.
    echo       Chay lenh nay truoc:
    echo         cd /d "%BACKEND%"
    echo         python -m venv .venv
    echo         .venv\Scripts\python.exe -m pip install -r requirements-dev.txt
    goto :fail
)
if not exist "%FRONTEND%\node_modules" (
    echo [LOI] Chua cai thu vien cua website.
    echo       Chay lenh nay truoc:
    echo         cd /d "%FRONTEND%"
    echo         npm install
    goto :fail
)
if not exist "%BACKEND%\.env" (
    echo [LOI] Thieu file "%BACKEND%\.env" - backend khong biet mat khau database.
    goto :fail
)

rem --- 1. Docker ----------------------------------------------------
echo [1/5] Kiem tra Docker...
docker info >nul 2>&1
if not errorlevel 1 (
    echo       Docker da san sang.
    goto :docker_ready
)

if not exist "%DOCKER_EXE%" (
    echo [LOI] Khong tim thay Docker Desktop tai:
    echo       %DOCKER_EXE%
    echo       Mo Docker Desktop thu cong roi chay lai script nay.
    goto :fail
)

echo       Docker chua chay. Dang bat Docker Desktop...
start "" "%DOCKER_EXE%"
echo       Doi Docker khoi dong (co the mat 1-2 phut)...

set /a _tries=0
:wait_docker
call :sleep 3
docker info >nul 2>&1
if not errorlevel 1 goto :docker_ready
set /a _tries+=1
if %_tries% GEQ 60 (
    echo.
    echo [LOI] Doi Docker qua 3 phut van chua san sang.
    echo       Kiem tra Docker Desktop roi chay lai script nay.
    goto :fail
)
echo       ... van dang doi Docker (%_tries%/60)
goto :wait_docker

:docker_ready

rem --- 2. DataPro.Client --------------------------------------------
echo [2/5] Kiem tra DataPro.Client...
tasklist /FI "IMAGENAME eq DataPro.Client.exe" 2>nul | find /I "DataPro.Client.exe" >nul
if not errorlevel 1 (
    echo       DataPro.Client dang chay.
) else (
    if exist "%DATAPRO_EXE%" (
        echo       Dang bat DataPro.Client...
        start "" "%DATAPRO_EXE%"
        call :sleep 5
    ) else (
        echo       [CANH BAO] Khong thay DataPro.Client. Website van chay duoc
        echo                  voi du lieu da co, nhung se khong co du lieu moi.
    )
)

rem --- 3. Container database ----------------------------------------
echo [3/5] Kiem tra database...
if not exist "%DBDIR%\docker-compose.yml" (
    echo [LOI] Khong thay database tai: %DBDIR%
    goto :fail
)
pushd "%DBDIR%"
docker compose up -d
if errorlevel 1 (
    popd
    echo [LOI] Khong bat duoc container database.
    goto :fail
)
popd
echo       TimescaleDB + Redis + ingestion da san sang.

rem --- 4. Backend + website -----------------------------------------
rem Chay script lan hai khong duoc mo them ban sao: cong da co nguoi tra loi
rem thi bo qua, neu khong uvicorn/next se chet vi "port already in use".
echo [4/5] Kiem tra backend (cong 8000)...
curl.exe -s -o nul --max-time 3 http://127.0.0.1:8000/healthz >nul 2>&1
if not errorlevel 1 (
    echo       Backend da chay san - bo qua.
    goto :api_ready
)

echo       Mo backend...
rem /D dat thu muc lam viec cho cua so moi. Dung /D thay vi "cd" de tranh
rem loi dau ngoac long nhau khi duong dan co khoang trang.
start "QP Backend :8000" /D "%BACKEND%" cmd /k .venv\Scripts\python.exe -m uvicorn app.main:app --reload

echo       Doi backend tra loi...
set /a _tries=0
:wait_api
call :sleep 2
curl.exe -s -o nul http://127.0.0.1:8000/healthz >nul 2>&1
if not errorlevel 1 goto :api_ready
set /a _tries+=1
if %_tries% GEQ 30 (
    echo       [CANH BAO] Backend chua tra loi sau 60 giay.
    echo                  Xem cua so "QP Backend" de biet loi.
    goto :api_ready
)
goto :wait_api
:api_ready

echo [5/5] Kiem tra website (cong 3000)...
curl.exe -s -o nul --max-time 3 http://127.0.0.1:3000/vi >nul 2>&1
if not errorlevel 1 (
    echo       Website da chay san - bo qua.
    goto :web_ready
)

echo       Mo website...
start "QP Website :3000" /D "%FRONTEND%" cmd /k npm run dev

echo       Doi website bien dich...
set /a _tries=0
:wait_web
call :sleep 3
curl.exe -s -o nul http://127.0.0.1:3000/vi >nul 2>&1
if not errorlevel 1 goto :web_ready
set /a _tries+=1
if %_tries% GEQ 40 (
    echo       [CANH BAO] Website chua len sau 2 phut.
    echo                  Xem cua so "QP Website" de biet loi.
    goto :done
)
goto :wait_web
:web_ready

start "" http://localhost:3000

:done
echo.
echo ==========================================
echo   XONG
echo.
echo   Website : http://localhost:3000
echo   API     : http://localhost:8000/docs
echo   Kiem tra: http://localhost:8000/readyz
echo.
echo   De tat: dong 2 cua so "QP Backend" va "QP Website".
echo           Database van chay nen - dung tat neu con dung.
echo ==========================================
echo.
echo Cua so nay dong duoc roi (tu dong dong sau 15 giay).
call :sleep 15
exit /b 0

:fail
echo.
echo Khoi dong that bai. Doc thong bao ben tren.
echo.
pause
exit /b 1
