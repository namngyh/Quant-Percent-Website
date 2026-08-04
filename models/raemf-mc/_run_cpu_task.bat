@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
cd /d "%ROOT%"

set "TASK_LABEL=%~1"
set "TASK_COMMAND=%~2"
set "TASK_CONFIG=%~3"
if "%TASK_LABEL%"=="" goto :usage
if "%TASK_COMMAND%"=="" goto :usage
if "%TASK_CONFIG%"=="" goto :usage

set "PYTHON_ARGS="
if exist "%ROOT%.venv\Scripts\python.exe" (
  set "PYTHON_EXE=%ROOT%.venv\Scripts\python.exe"
) else (
  for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$p=Get-Command python.exe -ErrorAction SilentlyContinue; if($p){$p.Source}"`) do set "PYTHON_EXE=%%P"
  if not defined PYTHON_EXE (
    where py.exe >nul 2>&1
    if errorlevel 1 goto :no_python
    set "PYTHON_EXE=py.exe"
    set "PYTHON_ARGS=-3"
  )
)

set "PYTHONPATH=%ROOT%src;%PYTHONPATH%"
if not defined RAEMF_DATA set "RAEMF_DATA=VNINDEX_Daily.csv"
if not exist "%RAEMF_DATA%" goto :no_data
if not exist "%TASK_CONFIG%" goto :no_config
if not exist "%ROOT%logs" mkdir "%ROOT%logs"
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "RUN_STAMP=%%I"
set "LOG_FILE=%ROOT%logs\%TASK_LABEL%_%RUN_STAMP%.log"

echo Python: "%PYTHON_EXE%" %PYTHON_ARGS%
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import os; print('Logical CPU threads:', os.cpu_count())"
if errorlevel 1 goto :failed_without_log
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import ctypes; M=type('M',(ctypes.Structure,),{'_fields_':[('dwLength',ctypes.c_ulong),('dwMemoryLoad',ctypes.c_ulong),('ullTotalPhys',ctypes.c_ulonglong),('ullAvailPhys',ctypes.c_ulonglong),('x1',ctypes.c_ulonglong),('x2',ctypes.c_ulonglong),('x3',ctypes.c_ulonglong),('x4',ctypes.c_ulonglong),('x5',ctypes.c_ulonglong)]}); m=M(); m.dwLength=ctypes.sizeof(M); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)); print('Available RAM (GiB):', round(m.ullAvailPhys/1024**3,2))"

echo Checking CPU dependencies...
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import arch,hmmlearn,interpret,numpy,pandas,sklearn,yaml; import raemf_mc; print('Core dependencies: OK')"
if errorlevel 1 goto :failed_without_log
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import importlib.util; s=importlib.util.find_spec('torch'); print('Torch installed:', bool(s)); exec(\"import torch; print('CUDA available:', torch.cuda.is_available()); print('Torch threads:', torch.get_num_threads())\" if s else \"\")"
if errorlevel 1 goto :failed_without_log

echo Running %TASK_LABEL%. Log: %LOG_FILE%
if /I "%TASK_COMMAND%"=="shadow-update" (
  "%PYTHON_EXE%" %PYTHON_ARGS% -m raemf_mc.cli shadow-update --data "%RAEMF_DATA%" --config "%TASK_CONFIG%" > "%LOG_FILE%" 2>&1
) else (
  "%PYTHON_EXE%" %PYTHON_ARGS% -m raemf_mc.cli downside-experiment --data "%RAEMF_DATA%" --config "%TASK_CONFIG%" > "%LOG_FILE%" 2>&1
)
set "TASK_EXIT=%ERRORLEVEL%"
type "%LOG_FILE%"
if not "%TASK_EXIT%"=="0" goto :failed
echo Completed successfully.
exit /b 0

:usage
echo Usage: _run_cpu_task.bat LABEL COMMAND CONFIG
goto :failed_without_log

:no_python
echo ERROR: Python 3 or .venv\Scripts\python.exe was not found.
goto :failed_without_log

:no_data
echo ERROR: Data file "%RAEMF_DATA%" was not found.
goto :failed_without_log

:no_config
echo ERROR: Config file "%TASK_CONFIG%" was not found.
goto :failed_without_log

:failed
echo ERROR: Task failed with exit code %TASK_EXIT%. See "%LOG_FILE%".
if not defined CI pause
exit /b %TASK_EXIT%

:failed_without_log
echo ERROR: CPU task could not start.
if not defined CI pause
exit /b 1
