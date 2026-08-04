@echo off
call "%~dp0_run_cpu_task.bat" cpu_smoke downside-experiment configs\cpu_smoke.yaml
exit /b %ERRORLEVEL%
