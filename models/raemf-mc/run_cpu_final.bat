@echo off
call "%~dp0_run_cpu_task.bat" cpu_final downside-experiment configs\cpu_final.yaml
exit /b %ERRORLEVEL%
