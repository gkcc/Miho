@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0build_miho_probe_exe.ps1" %*
exit /b %ERRORLEVEL%
