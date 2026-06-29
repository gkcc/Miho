@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0install_miho_demo_shortcut.ps1" %*
exit /b %ERRORLEVEL%
