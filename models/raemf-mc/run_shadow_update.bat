@echo off
call "%~dp0_run_cpu_task.bat" shadow_update shadow-update configs\cpu_final.yaml
exit /b %ERRORLEVEL%
