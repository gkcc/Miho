@echo off
set "EXE=%~dp0..\dist\MihoProbe.exe"
set "KEEP_OPEN=1"
if "%~1"=="--help-only" set "KEEP_OPEN=0"
if not exist "%EXE%" (
  echo Missing dist\MihoProbe.exe.
  echo Build it first:
  echo   powershell -ExecutionPolicy Bypass -File scripts\build_miho_probe_exe.ps1
  echo.
  pause
  exit /b 1
)

echo MihoProbe local dashboard entry
echo.
"%EXE%" dashboard --open
echo.
echo Common examples:
echo   dist\MihoProbe.exe dashboard --open
echo   dist\MihoProbe.exe app-export --open
echo   dist\MihoProbe.exe app-export-calibrate --open
echo   dist\MihoProbe.exe app-export-run --no-open
echo   dist\MihoProbe.exe update --open
echo   dist\MihoProbe.exe plan-update --open
echo   dist\MihoProbe.exe box-roster --image data\probes\exported_images\zzz_box.png --no-open
echo   dist\MihoProbe.exe box-value --box-image data\probes\exported_images\zzz_box.png --meta-snapshot data\probes\meta\zzz_prydwen_meta_all_phases.json
echo   dist\MihoProbe.exe rank-check --open
echo   dist\MihoProbe.exe fresh --open
echo   dist\MihoProbe.exe check --no-open
echo   dist\MihoProbe.exe replay --no-open
echo   dist\MihoProbe.exe ask-gpt --focus "本轮要审的问题" --evidence "关键证据"
echo   dist\MihoProbe.exe demo --images-dir figs --open
echo   dist\MihoProbe.exe demo --parsed-dir data\probes\parsed --latest-only --open
echo   dist\MihoProbe.exe normalize --parsed data\probes\parsed\xxx.json
echo.
echo Full help:
"%EXE%" --help
echo.
if "%KEEP_OPEN%"=="1" cmd /k
