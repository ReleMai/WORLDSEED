@echo off
setlocal
cd /d "%~dp0"
if not exist "WORLDSEED_GPU.exe" (
  echo Missing WORLDSEED_GPU.exe. Extract the complete Windows GPU CANDIDATE artifact.
  pause
  exit /b 2
)
if not exist "logs" mkdir "logs"
echo WORLDSEED GPU candidate - temporary new world; no existing saves are opened.
echo Requires desktop OpenGL 3.3 or newer. Startup logs stay in this folder.
"WORLDSEED_GPU.exe" --report "logs\gpu-new-world.json" > "logs\gpu-new-world.log" 2>&1
set "GAME_EXIT=%ERRORLEVEL%"
echo GPU candidate exited with code %GAME_EXIT%. See logs\gpu-new-world.log
if not "%GAME_EXIT%"=="0" type "logs\gpu-new-world.log"
pause
exit /b %GAME_EXIT%
