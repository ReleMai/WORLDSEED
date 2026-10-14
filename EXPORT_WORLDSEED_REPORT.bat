@echo off
setlocal
cd /d "%~dp0"
if not exist "WORLDSEED.exe" (
  echo Please extract the complete Windows build before exporting.
  pause
  exit /b 2
)
"WORLDSEED.exe" --playtest-export
if errorlevel 1 (
  echo Report generation failed.
) else (
  if exist "playtest_reports" explorer.exe "playtest_reports"
)
pause
