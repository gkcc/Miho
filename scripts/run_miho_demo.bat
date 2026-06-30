@echo off
setlocal
set "EXE=%~dp0..\dist\MihoProbe.exe"
set "BUILD=%~dp0build_miho_probe_exe.bat"

if not exist "%EXE%" (
  echo MihoProbe executable is missing:
  echo   "%EXE%"
  echo.
  echo This launcher is EXE-first and will not fall back to the slow Python image-recognition path by default.
  echo Build it first:
  echo   "%BUILD%"
  echo.
  echo Legacy Python launcher is still available for development:
  echo   powershell -ExecutionPolicy Bypass -File "%~dp0run_miho_demo.ps1" --help
  exit /b 1
)

if "%~1"=="" (
  echo [MihoProbe] Opening cached Dashboard only. Image recognition will NOT run.
  echo [MihoProbe] If you only want to inspect the UI, this is the right entry.
  echo [MihoProbe] Slow image recognition is only started by: scripts\run_miho_demo.bat --fresh
  "%EXE%" dashboard --open
  exit /b %ERRORLEVEL%
)
if /I "%~1"=="--fresh" (
  echo [MihoProbe] Image recognition requested. This can be slow because it loads the recognition model.
  echo [MihoProbe] For UI acceptance, close this and run scripts\run_miho_demo.bat without --fresh.
  "%EXE%" fresh --open
  exit /b %ERRORLEVEL%
)
if /I "%~1"=="-fresh" (
  echo [MihoProbe] Image recognition requested. This can be slow because it loads the recognition model.
  echo [MihoProbe] For UI acceptance, close this and run scripts\run_miho_demo.bat without --fresh.
  "%EXE%" fresh --open
  exit /b %ERRORLEVEL%
)
if /I "%~1"=="/fresh" (
  echo [MihoProbe] Image recognition requested. This can be slow because it loads the recognition model.
  echo [MihoProbe] For UI acceptance, close this and run scripts\run_miho_demo.bat without --fresh.
  "%EXE%" fresh --open
  exit /b %ERRORLEVEL%
)
if /I "%~1"=="--open-only" (
  echo [MihoProbe] Opening cached Dashboard only. Image recognition will NOT run.
  "%EXE%" dashboard --open
  exit /b %ERRORLEVEL%
)
if /I "%~1"=="-open-only" (
  echo [MihoProbe] Opening cached Dashboard only. Image recognition will NOT run.
  "%EXE%" dashboard --open
  exit /b %ERRORLEVEL%
)
if /I "%~1"=="/open-only" (
  echo [MihoProbe] Opening cached Dashboard only. Image recognition will NOT run.
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

"%EXE%" %*
exit /b %ERRORLEVEL%
