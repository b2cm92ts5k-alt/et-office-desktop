# ET Office — build .exe ด้วย PyInstaller (M5-3)
# รัน:  powershell -ExecutionPolicy Bypass -File installer\build.ps1
# ได้:  dist\ET-Office\  (ET-Office.exe + et-office-daemon.exe + et-office-sidebar.exe)
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
Set-Location $repo

if (-not (Test-Path .venv\Scripts\python.exe)) {
    Write-Host "[BUILD] .venv not found - see Quick Start in README.md"; exit 1
}

Write-Host "[BUILD] PyInstaller..." -ForegroundColor Cyan
.venv\Scripts\python.exe -m PyInstaller installer\et-office.spec --noconfirm --clean `
    --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { Write-Host "[BUILD] FAILED"; exit 1 }

# ตัว Godot export (M5-4) วางเพิ่มเองที่ dist\ET-Office\et-office-wallpaper.exe
$out = Join-Path $repo "dist\ET-Office"
$size = "{0:N0} MB" -f ((Get-ChildItem $out -Recurse | Measure-Object Length -Sum).Sum / 1MB)
Write-Host "[BUILD] done -> $out ($size)" -ForegroundColor Green
