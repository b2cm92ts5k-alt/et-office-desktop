@echo off
REM ET Office - open sidebar UI (double-click to run; daemon must be running first)
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo [ET OFFICE] .venv not found - see Quick Start in README.md
    pause
    exit /b 1
)
.venv\Scripts\python.exe sidebar\host.py %*
