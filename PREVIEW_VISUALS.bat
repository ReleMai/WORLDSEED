@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto python
py -3.13 -c "import pygame" >nul 2>nul
if errorlevel 1 goto pydefault
py -3.13 tools\preview_weather_visuals.py
if errorlevel 1 pause
exit /b
:pydefault
py -3 tools\preview_weather_visuals.py
if errorlevel 1 pause
exit /b
:python
python tools\preview_weather_visuals.py
if errorlevel 1 pause
