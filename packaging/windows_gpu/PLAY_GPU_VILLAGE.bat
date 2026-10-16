@echo off
setlocal
cd /d "%~dp0"
if not exist "WORLDSEED_GPU.exe" (
  echo Missing WORLDSEED_GPU.exe. Extract the complete Windows GPU CANDIDATE artifact.
  pause
  exit /b 2
)
if not exist "logs" mkdir "logs"
echo WORLDSEED synthetic village QA - snow, winter, noon; actual plans and private interiors.
"WORLDSEED_GPU.exe" --prepared-scene village_street --qa-weather snow --qa-season winter --qa-time noon --report "logs\gpu-village.json" > "logs\gpu-village.log" 2>&1
set "GAME_EXIT=%ERRORLEVEL%"
echo GPU candidate exited with code %GAME_EXIT%. See logs\gpu-village.log
if not "%GAME_EXIT%"=="0" type "logs\gpu-village.log"
pause
exit /b %GAME_EXIT%
