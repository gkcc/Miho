@echo off
setlocal
set "EXE=%~dp0..\dist\MihoProbe.exe"

if exist "%EXE%" (
  if "%~1"=="" (
    "%EXE%" dashboard --open
    exit /b %ERRORLEVEL%
  )
  if /I "%~1"=="--fresh" (
    "%EXE%" fresh --open
    exit /b %ERRORLEVEL%
  )
  if /I "%~1"=="-fresh" (
    "%EXE%" fresh --open
    exit /b %ERRORLEVEL%
  )
  if /I "%~1"=="/fresh" (
    "%EXE%" fresh --open
    exit /b %ERRORLEVEL%
  )
  if /I "%~1"=="--open-only" (
    "%EXE%" dashboard --open
    exit /b %ERRORLEVEL%
  )
  if /I "%~1"=="-open-only" (
    "%EXE%" dashboard --open
    exit /b %ERRORLEVEL%
  )
  if /I "%~1"=="/open-only" (
    "%EXE%" dashboard --open
    exit /b %ERRORLEVEL%
  )
  if /I "%~1"=="--help" (
    "%EXE%" --help
    exit /b %ERRORLEVEL%
  )
  if /I "%~1"=="-help" (
    "%EXE%" --help
    exit /b %ERRORLEVEL%
  )
  if "%~1"=="/?" (
    "%EXE%" --help
    exit /b %ERRORLEVEL%
  )
)

powershell -ExecutionPolicy Bypass -File "%~dp0run_miho_demo.ps1" %*
exit /b %ERRORLEVEL%
