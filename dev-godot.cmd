@echo off
REM ET Office — เปิด Godot โหมด window สำหรับตรวจภาพ (ดับเบิลคลิกได้เลย)
REM ส่ง arg เพิ่มได้ เช่น:  dev-godot.cmd --wallpaper   หรือ  dev-godot.cmd --write-movie demo.avi --fixed-fps 30
cd /d "%~dp0"
set "GODOT="
for /f "delims=" %%G in ('dir /b /s "%LOCALAPPDATA%\Microsoft\WinGet\Packages\Godot_v*-stable_win64.exe" 2^>nul') do set "GODOT=%%G"
if not defined GODOT (
    echo [ET OFFICE] หา Godot ไม่เจอใน WinGet Packages — ติดตั้งด้วย: winget install GodotEngine.GodotEngine
    pause
    exit /b 1
)
echo [ET OFFICE] %GODOT%
if "%~1"=="--wallpaper" (
    "%GODOT%" --path godot -- --wallpaper
) else (
    "%GODOT%" --path godot %*
)
