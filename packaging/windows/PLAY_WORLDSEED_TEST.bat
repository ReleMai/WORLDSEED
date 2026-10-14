@echo off
setlocal
cd /d "%~dp0"
if not exist "WORLDSEED.exe" (
  echo.
  echo ERROR: WORLDSEED.exe is not beside this launcher.
  echo.
  echo You probably downloaded Code ^> Download ZIP ^(source code only^).
  echo That download includes Python files, but NOT the compiled Windows EXE.
  echo.
  echo Get the 400+ MB Windows x64 EXECUTABLE artifact from:
  echo https://github.com/ReleMai/WORLDSEED/actions/workflows/windows-playtest.yml
  echo Open the latest successful run, scroll to Artifacts, and download
  echo WORLDSEED-Windows-x64-EXECUTABLE-...
  echo.
  echo Extract that artifact into a NEW EMPTY folder. Keep _internal with the EXE.
  echo Do not merge it with an old WORLDSEED source folder.
  pause
  exit /b 2
)
if not exist "logs" mkdir "logs"
echo WORLDSEED Windows Playtest - diagnostic capture enabled
echo Logs and reports remain on this computer. Nothing is uploaded automatically.
echo Close WORLDSEED normally to package your latest play session.
"WORLDSEED.exe" --window --profile-runtime >> "logs\PLAYTEST_LAUNCHER.log" 2>&1
set "GAME_EXIT=%ERRORLEVEL%"
echo %GAME_EXIT% > PLAYTEST_LAST_EXIT.txt
echo.
echo WORLDSEED exited with code %GAME_EXIT%.
echo Preparing a shareable diagnostic ZIP without saves or raw keyboard input...
"WORLDSEED.exe" --playtest-export
if errorlevel 1 (
  echo Diagnostic export failed. Check logs\PLAYTEST_LAUNCHER.log locally.
) else (
  echo Report created in playtest_reports
  if exist "playtest_reports" explorer.exe "playtest_reports"
)
echo Upload the newest WORLDSEED_PLAYTEST_REPORT_*.zip to your ChatGPT project.
pause
