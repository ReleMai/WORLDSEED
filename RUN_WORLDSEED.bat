@echo off
setlocal
where py >nul 2>nul
if %errorlevel%==0 (
    set PY=py -3
) else (
    set PY=python
)

%PY% -c "import pygame" >nul 2>nul
if errorlevel 1 (
    echo WORLDSEED visual renderer requires pygame-ce.
    echo Installing pygame-ce into the active Python environment...
    %PY% -m pip install "pygame-ce>=2.5.3,<3"
)

%PY% -c "import pygame" >nul 2>nul
if errorlevel 1 (
    echo.
    echo pygame-ce could not be installed. Falling back to the legacy terminal renderer.
    %PY% run_worldseed.py --terminal
) else (
    %PY% run_worldseed.py --window
)

echo.
pause
