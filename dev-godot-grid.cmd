@echo off
REM ET Office - เปิด Godot (window mode) พร้อม overlay เลขพิกัด (gx,gy) ทุก tile
REM ใช้หา cell ที่จะใส่ใน office_builder.gd FURNITURE / neon_signs.gd SIGN_GRID
REM ดับเบิลคลิกไฟล์นี้ได้เลย
cd /d "%~dp0"
set "GODOT="
for /f "delims=" %%G in ('dir /b /s "%LOCALAPPDATA%\Microsoft\WinGet\Packages\Godot_v*-stable_win64.exe" 2^>nul') do set "GODOT=%%G"
if not defined GODOT (
    echo [ET OFFICE] Godot not found - winget install GodotEngine.GodotEngine
    pause
    exit /b 1
)
echo [ET OFFICE] grid overlay ON: %GODOT%
"%GODOT%" --path godot -- --grid
