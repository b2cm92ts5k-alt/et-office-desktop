@echo off
REM ET Office - open Godot in window mode for visual checks (double-click to run)
REM Extra args pass through, e.g.:  dev-godot.cmd --wallpaper
REM                                 dev-godot.cmd --write-movie demo.avi --fixed-fps 30
cd /d "%~dp0"
set "GODOT="
for /f "delims=" %%G in ('dir /b /s "%LOCALAPPDATA%\Microsoft\WinGet\Packages\Godot_v*-stable_win64.exe" 2^>nul') do set "GODOT=%%G"
if not defined GODOT (
    echo [ET OFFICE] Godot not found in WinGet Packages - install with: winget install GodotEngine.GodotEngine
    pause
    exit /b 1
)
echo [ET OFFICE] %GODOT%
if "%~1"=="--wallpaper" (
    "%GODOT%" --path godot -- --wallpaper
) else (
    "%GODOT%" --path godot %*
)
