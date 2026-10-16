@echo off
setlocal
cd /d "%~dp0"
if not exist "WORLDSEED_GPU.exe" (
  echo Missing WORLDSEED_GPU.exe. Extract the complete Windows GPU artifact.
  pause
  exit /b 2
)
echo WORLDSEED main game with the new GPU renderer.
echo New Game, Load Game, all command screens, autosave and Save and Quit use the main game.
echo Saves and diagnostics: %LOCALAPPDATA%\WORLDSEED
echo Gameplay crash report: %LOCALAPPDATA%\WORLDSEED\WORLDSEED_CRASH.log
echo Double-click OPEN_LOGS.bat to find crash and session logs.
"WORLDSEED_GPU.exe"
set "GAME_EXIT=%ERRORLEVEL%"
if not "%GAME_EXIT%"=="0" (
  echo WORLDSEED exited with code %GAME_EXIT%. Double-click OPEN_LOGS.bat for diagnostics.
  pause
)
exit /b %GAME_EXIT%
