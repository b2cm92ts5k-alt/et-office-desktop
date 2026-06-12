# ET Office Desktop - one-shot installer (M5-2)
#
#   1) ตรวจ WebView2 runtime (sidebar ต้องใช้) - ไม่มีก็ติดตั้งเงียบ ๆ
#   2) ตรวจ/ติดตั้ง Ollama + ปลุกให้ตื่น
#   3) ตรวจ VRAM (nvidia-smi) -> เลือก model ตาม MODEL_MAP เดียวกับ daemon -> ollama pull
#   4) ติดตั้ง app ลง %LOCALAPPDATA%\ET-Office + shortcut Desktop/Start Menu
#
# รัน (คลิกขวา install.ps1 -> Run with PowerShell หรือ):
#   powershell -ExecutionPolicy Bypass -File install.ps1
# ตัวเลือก: -NoLaunch (ไม่เปิด app หลังติดตั้ง) | -SkipModel (ข้าม pull) |
#           -Source <path ของโฟลเดอร์ ET-Office> (default: หาเอง)
param(
    [switch]$NoLaunch,
    [switch]$SkipModel,
    [string]$Source = ""
)
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = "SilentlyContinue"

function Step($msg)  { Write-Host "`n== $msg" -ForegroundColor Cyan }
function Ok($msg)    { Write-Host "   $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "   $msg" -ForegroundColor Yellow }

$InstallDir = Join-Path $env:LOCALAPPDATA "ET-Office"

# --- 0) หาตัว app ----------------------------------------------------------
# release zip: install.ps1 อยู่ข้างโฟลเดอร์ ET-Office | dev: รันจาก repo หลัง build.ps1
if (-not $Source) {
    foreach ($cand in @((Join-Path $PSScriptRoot "ET-Office"),
                        (Join-Path (Split-Path $PSScriptRoot -Parent) "dist\ET-Office"))) {
        if (Test-Path (Join-Path $cand "ET-Office.exe")) { $Source = $cand; break }
    }
}
if (-not $Source -or -not (Test-Path (Join-Path $Source "ET-Office.exe"))) {
    Write-Host "ไม่พบโฟลเดอร์ ET-Office (ตัว app) - แตก zip ให้ครบก่อน หรือรัน installer\build.ps1" -ForegroundColor Red
    exit 1
}

# --- 1) WebView2 runtime ----------------------------------------------------
Step "ตรวจ WebView2 runtime"
$wv2Keys = @(
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
    "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
)
$wv2 = $wv2Keys | Where-Object { Test-Path $_ } |
    ForEach-Object { (Get-ItemProperty $_ -ErrorAction SilentlyContinue).pv } |
    Where-Object { $_ -and $_ -ne "0.0.0.0" } | Select-Object -First 1
if ($wv2) { Ok "มีแล้ว (v$wv2)" }
else {
    Warn "ไม่พบ - ดาวน์โหลด bootstrapper จาก Microsoft..."
    $wvSetup = Join-Path $env:TEMP "MicrosoftEdgeWebView2Setup.exe"
    Invoke-WebRequest -UseBasicParsing "https://go.microsoft.com/fwlink/p/?LinkId=2124703" -OutFile $wvSetup
    Start-Process $wvSetup -ArgumentList "/silent", "/install" -Wait
    Ok "ติดตั้ง WebView2 แล้ว"
}

# --- 2) Ollama --------------------------------------------------------------
Step "ตรวจ Ollama"
$ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if (-not $ollama) {
    $cand = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path $cand) { $ollama = $cand }
}
if ($ollama) { Ok "มีแล้ว ($ollama)" }
else {
    Warn "ไม่พบ - ติดตั้งผ่าน winget..."
    winget install --id Ollama.Ollama --accept-source-agreements --accept-package-agreements --silent
    if ($LASTEXITCODE -ne 0) {
        Warn "winget ไม่สำเร็จ - ดาวน์โหลด OllamaSetup ตรง..."
        $oSetup = Join-Path $env:TEMP "OllamaSetup.exe"
        Invoke-WebRequest -UseBasicParsing "https://ollama.com/download/OllamaSetup.exe" -OutFile $oSetup
        Start-Process $oSetup -ArgumentList "/VERYSILENT" -Wait
    }
    $ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (-not (Test-Path $ollama)) {
        Write-Host "ติดตั้ง Ollama ไม่สำเร็จ - ติดตั้งเองจาก https://ollama.com แล้วรัน installer ใหม่" -ForegroundColor Red
        exit 1
    }
    Ok "ติดตั้ง Ollama แล้ว"
}

# ปลุก ollama ถ้ายังไม่ตื่น
try { Invoke-RestMethod "http://127.0.0.1:11434/api/version" -TimeoutSec 3 | Out-Null; Ok "Ollama ทำงานอยู่" }
catch {
    Warn "ปลุก Ollama..."
    Start-Process $ollama -ArgumentList "serve" -WindowStyle Hidden
    $up = $false
    foreach ($i in 1..20) {
        Start-Sleep 1
        try { Invoke-RestMethod "http://127.0.0.1:11434/api/version" -TimeoutSec 2 | Out-Null; $up = $true; break } catch {}
    }
    if ($up) { Ok "Ollama พร้อม" } else { Warn "Ollama ยังไม่ตอบ - app จะแจ้งอีกทีตอนเปิด" }
}

# --- 3) VRAM detect -> pull model -------------------------------------------
if (-not $SkipModel) {
    Step "ตรวจ VRAM เลือก model"
    $vram = 0.0
    try {
        $mb = (& nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>$null |
               Select-Object -First 1)
        if ($mb) { $vram = [double]$mb / 1024 }
    } catch {}
    # MODEL_MAP เดียวกับ daemon/adapters/llm_adapter.py (คอลัมน์ qwen)
    $model = if ($vram -lt 4) { "qwen2.5:1.5b" }
             elseif ($vram -lt 16) { "qwen3:8b" }
             else { "qwen3:32b" }
    Ok ("VRAM {0:N1} GB -> {1}" -f $vram, $model)
    $have = (& $ollama list 2>$null) -match [regex]::Escape($model)
    if ($have) { Ok "model มีอยู่แล้ว" }
    else {
        Warn "กำลัง pull $model (ครั้งเดียว อาจหลายนาที)..."
        & $ollama pull $model
        if ($LASTEXITCODE -ne 0) { Warn "pull ไม่สำเร็จ - ลองเองทีหลัง: ollama pull $model" }
        else { Ok "pull เสร็จ" }
    }
}

# --- 4) ติดตั้ง app + shortcuts ----------------------------------------------
Step "ติดตั้ง app -> $InstallDir"
robocopy $Source $InstallDir /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { Write-Host "copy ล้มเหลว (robocopy $LASTEXITCODE)" -ForegroundColor Red; exit 1 }
$LASTEXITCODE = 0
Ok ("คัดลอกแล้ว ({0:N0} MB)" -f ((Get-ChildItem $InstallDir -Recurse | Measure-Object Length -Sum).Sum / 1MB))

$shell = New-Object -ComObject WScript.Shell
foreach ($lnkDir in @([Environment]::GetFolderPath("Desktop"),
                      (Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs"))) {
    $lnk = $shell.CreateShortcut((Join-Path $lnkDir "ET Office.lnk"))
    $lnk.TargetPath = Join-Path $InstallDir "ET-Office.exe"
    $lnk.WorkingDirectory = $InstallDir
    $lnk.Description = "ET Office Desktop - cyberpunk AI agent office wallpaper"
    $lnk.Save()
}
Ok "สร้าง shortcut Desktop + Start Menu แล้ว"

Write-Host "`n=== ติดตั้งเสร็จ ===" -ForegroundColor Green
Write-Host "เปิด: shortcut 'ET Office' หรือ $InstallDir\ET-Office.exe"
Write-Host "ถอนการติดตั้ง: ลบโฟลเดอร์ $InstallDir + shortcut ทั้งสองจุด (ไม่มี registry)"
if (-not $NoLaunch) {
    $ans = Read-Host "เปิด ET Office เลยไหม? (Y/n)"
    if ($ans -ne "n") { Start-Process (Join-Path $InstallDir "ET-Office.exe") -WorkingDirectory $InstallDir }
}
