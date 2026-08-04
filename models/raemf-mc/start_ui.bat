@echo off
rem Khoi dong web UI local cua RAEMF-MC roi mo trinh duyet.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [LOI] Khong tim thay .venv\Scripts\python.exe. Hay tao moi truong ao truoc.
    pause
    exit /b 1
)

set "RAEMF_ROOT=%~dp0"
start "" http://127.0.0.1:8600
".venv\Scripts\python.exe" -m uvicorn raemf_mc.webapp.app:app --host 127.0.0.1 --port 8600
pause
