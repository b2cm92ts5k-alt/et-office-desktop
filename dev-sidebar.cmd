@echo off
REM ET Office — เปิด sidebar UI (ดับเบิลคลิกได้เลย — daemon ต้องรันอยู่ก่อน)
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo [ET OFFICE] ไม่พบ .venv — ดู Quick Start ใน README.md
    pause
    exit /b 1
)
.venv\Scripts\python.exe sidebar\host.py %*
