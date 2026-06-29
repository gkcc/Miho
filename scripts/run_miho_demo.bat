@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0run_miho_demo.ps1" %*
exit /b %ERRORLEVEL%
