@echo off
REM ET Office Desktop — quick dev launcher (placeholder จนกว่า shell/launcher.py จะเสร็จใน M5-1)
cd /d "%~dp0"
echo [ET OFFICE] starting daemon on port 8797...
.venv\Scripts\python.exe -m uvicorn daemon.main:app --port 8797
