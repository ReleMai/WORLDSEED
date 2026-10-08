@echo off
cd /d "%~dp0"
python run_npc_job_lab.py %*
if errorlevel 1 pause
