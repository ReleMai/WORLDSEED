@echo off
setlocal
set "WORLDSEED_RUNTIME=%LOCALAPPDATA%\WORLDSEED"
if not defined LOCALAPPDATA set "WORLDSEED_RUNTIME=%USERPROFILE%\WORLDSEED"
echo WORLDSEED local diagnostics: %WORLDSEED_RUNTIME%
echo Gameplay crash: WORLDSEED_CRASH.log, also copied into logs in newer builds.
echo Session events: logs\WORLDSEED_DEBUG_*.jsonl
echo Startup or uncaught launch failure: logs\gpu-session.error.log
echo These files stay on this PC. Nothing is uploaded automatically.
if not exist "%WORLDSEED_RUNTIME%" (
  echo No runtime directory exists yet. Launch WORLDSEED_GPU.exe first.
  pause
  exit /b 1
)
start "" explorer.exe "%WORLDSEED_RUNTIME%"
