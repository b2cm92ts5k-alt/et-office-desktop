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

$out = Join-Path $repo "dist\ET-Office"

# --- Godot export (M5-4): et-office-wallpaper.exe + tools ps1 ข้าง launcher ---
$godot = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse `
    -Filter "Godot_v*-stable_win64.exe" -ErrorAction SilentlyContinue |
    Select-Object -First 1 -ExpandProperty FullName
if (-not $godot -and $env:GODOT_PATH) { $godot = $env:GODOT_PATH }
if ($godot) {
    Write-Host "[BUILD] Godot export..." -ForegroundColor Cyan
    & $godot --headless --path (Join-Path $repo "godot") --export-release "Windows Desktop" `
        (Join-Path $out "et-office-wallpaper.exe")
    if ($LASTEXITCODE -ne 0) { Write-Host "[BUILD] Godot export FAILED"; exit 1 }
    # wallpaper_manager.gd (packaged mode) หา exe_dir\tools\wallpaper.ps1
    New-Item -ItemType Directory -Force (Join-Path $out "tools") | Out-Null
    Copy-Item (Join-Path $repo "tools\wallpaper.ps1"), (Join-Path $repo "tools\fullscreen-watch.ps1") `
        (Join-Path $out "tools\")
} else {
    Write-Host "[BUILD] skip Godot export - Godot not found (winget install GodotEngine.GodotEngine)"
}

$size = "{0:N0} MB" -f ((Get-ChildItem $out -Recurse | Measure-Object Length -Sum).Sum / 1MB)
Write-Host "[BUILD] done -> $out ($size)" -ForegroundColor Green
