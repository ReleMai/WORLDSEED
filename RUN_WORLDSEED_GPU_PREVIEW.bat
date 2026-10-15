@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0worldseed\presentation\gl_atmosphere.py" (
 echo WORLDSEED GPU shader files missing. Fetch the latest main build.
 pause
 exit /b 1
)
py -3 -m tools.worldseed_gpu_playtest --scene forest
if errorlevel 1 (
 echo.
 echo GPU startup failed. Requires Python 3.11+, OpenGL 3.3 GPU drivers,
 echo and: py -3 -m pip install -e ".[gpu]"
 pause
)
endlocal
