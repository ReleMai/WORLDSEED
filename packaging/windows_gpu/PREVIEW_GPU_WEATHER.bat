@echo off
setlocal
cd /d "%~dp0"
if not exist "WORLDSEED_GPU.exe" (
  echo Missing WORLDSEED_GPU.exe. Extract the complete Windows GPU CANDIDATE artifact.
  pause
  exit /b 2
)
if not exist "logs" mkdir "logs"
echo WORLDSEED visual-only forest preview. F weather; 1-4 seasons; [/] sun; T torch.
echo Movement changes the preview camera only. This mode does not run gameplay commands.
"WORLDSEED_GPU.exe" --preview forest --report "logs\gpu-preview.json" > "logs\gpu-preview.log" 2>&1
set "GAME_EXIT=%ERRORLEVEL%"
echo GPU preview exited with code %GAME_EXIT%. See logs\gpu-preview.log
if not "%GAME_EXIT%"=="0" type "logs\gpu-preview.log"
pause
exit /b %GAME_EXIT%
