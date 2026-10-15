@echo off
setlocal
cd /d "%~dp0"
py -3 -m tools.worldseed_gpu_gameplay %*
if errorlevel 1 (
 echo.
 echo GPU candidate startup failed. Requires Python 3.11+, OpenGL 3.3 drivers,
 echo and: py -3 -m pip install -e ".[gpu]"
 pause
)
endlocal
