@echo off
setlocal
cd /d "%~dp0"
if not exist "WORLDSEED_GPU.exe" (
  echo Missing WORLDSEED_GPU.exe. Extract the complete Windows GPU CANDIDATE artifact.
  pause
  exit /b 2
)
if not exist "logs" mkdir "logs"
echo WORLDSEED synthetic camp QA - rain, autumn, sunset; authoritative gameplay commands.
"WORLDSEED_GPU.exe" --prepared-scene camp --qa-weather rain --qa-season autumn --qa-time sunset --report "logs\gpu-camp.json" > "logs\gpu-camp.log" 2>&1
set "GAME_EXIT=%ERRORLEVEL%"
echo GPU candidate exited with code %GAME_EXIT%. See logs\gpu-camp.log
if not "%GAME_EXIT%"=="0" type "logs\gpu-camp.log"
pause
exit /b %GAME_EXIT%
