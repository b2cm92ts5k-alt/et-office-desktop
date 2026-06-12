@echo off
REM ET Office Desktop - one-click launcher (M5-1): daemon + Godot wallpaper + sidebar
REM Extra args pass through, e.g.:  et-office.cmd --window      (Godot window mode)
REM                                 et-office.cmd --no-godot    (daemon + sidebar only)
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo [ET OFFICE] .venv not found - see Quick Start in README.md
    pause
    exit /b 1
)
.venv\Scripts\python.exe shell\launcher.py %*
pause
