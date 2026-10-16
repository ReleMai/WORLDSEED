@echo off
setlocal
cd /d "%~dp0"
if not exist "WORLDSEED_GPU.exe" (
  echo Missing WORLDSEED_GPU.exe. Extract the complete Windows GPU CANDIDATE artifact.
  pause
  exit /b 2
)
echo WORLDSEED main game with GPU graphics. Select New Game or Load Game.
echo This launcher now preserves progress; saves and diagnostics live in %LOCALAPPDATA%\WORLDSEED.
echo Gameplay crash report: %LOCALAPPDATA%\WORLDSEED\WORLDSEED_CRASH.log
echo Double-click OPEN_LOGS.bat to find crash and session logs.
"WORLDSEED_GPU.exe"
set "GAME_EXIT=%ERRORLEVEL%"
echo GPU game exited with code %GAME_EXIT%. See %LOCALAPPDATA%\WORLDSEED\logs
pause
exit /b %GAME_EXIT%
