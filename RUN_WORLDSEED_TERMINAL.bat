@echo off
setlocal
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 run_worldseed.py --terminal
) else (
    python run_worldseed.py --terminal
)
echo.
pause
