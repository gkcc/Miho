@echo off
set "EXE=%~dp0..\dist\MihoProbe.exe"
if not exist "%EXE%" (
  echo Missing dist\MihoProbe.exe.
  echo Build it first:
  echo   scripts\build_miho_probe_exe.bat
  echo.
  pause
  exit /b 1
)

echo MihoProbe ZZZ box / tier planner
echo.
echo Common examples:
echo   dist\MihoProbe.exe status
echo   dist\MihoProbe.exe meta --current-only
echo   dist\MihoProbe.exe box-roster --image data\probes\exported_images\zzz_box_overview.png
echo   dist\MihoProbe.exe box-value --roster-json data\probes\box\zzz_box_roster.json --meta-snapshot data\probes\meta\zzz_prydwen_meta_all_phases.json
echo   dist\MihoProbe.exe box-value --box-image data\probes\exported_images\zzz_box_overview.png --meta-snapshot data\probes\meta\zzz_prydwen_meta_all_phases.json
echo.
echo Full help:
"%EXE%" --help
echo.
cmd /k
