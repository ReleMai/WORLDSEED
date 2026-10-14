@echo off
setlocal
cd /d "%~dp0"
if not exist "WORLDSEED.exe" (
  echo Missing WORLDSEED.exe. The GitHub source ZIP is NOT the Windows build.
  echo Download a successful Windows x64 EXECUTABLE artifact from:
  echo https://github.com/ReleMai/WORLDSEED/actions/workflows/windows-playtest.yml
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
