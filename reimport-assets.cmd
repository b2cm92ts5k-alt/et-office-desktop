@echo off
REM ET Office - reimport sprite/asset ที่เพิ่งแก้ไข เข้า Godot cache
REM ดับเบิลคลิกไฟล์นี้ "ทุกครั้งหลังเปลี่ยนรูป .png" แล้วค่อยรัน dev-godot.cmd
REM (Godot ตอนรันเกมตรง ๆ ไม่ reimport ให้ — ใช้รูป cache เก่า ต้องสั่ง --import เอง)
cd /d "%~dp0"
set "GODOT="
for /f "delims=" %%G in ('dir /b /s "%LOCALAPPDATA%\Microsoft\WinGet\Packages\Godot_v*-stable_win64_console.exe" 2^>nul') do set "GODOT=%%G"
if not defined GODOT (
    for /f "delims=" %%G in ('dir /b /s "%LOCALAPPDATA%\Microsoft\WinGet\Packages\Godot_v*-stable_win64.exe" 2^>nul') do set "GODOT=%%G"
)
if not defined GODOT (
    echo [ET OFFICE] Godot not found - winget install GodotEngine.GodotEngine
    pause
    exit /b 1
)
echo [ET OFFICE] reimporting assets...
"%GODOT%" --headless --path godot --import
echo.
echo [ET OFFICE] reimport done - เปิด dev-godot.cmd ดูผลได้เลย
pause
