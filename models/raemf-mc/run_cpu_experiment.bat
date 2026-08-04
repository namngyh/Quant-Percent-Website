@echo off
call "%~dp0_run_cpu_task.bat" cpu_experiment downside-experiment configs\cpu_experiment.yaml
exit /b %ERRORLEVEL%
