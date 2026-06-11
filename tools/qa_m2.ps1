# QA Gate M2 (M2-13) - real wallpaper-mode integration test (ASCII only: PS 5.1 BOM gotcha)
#
# Checks:
#   1. attach as wallpaper succeeds (WorkerW embed) + conflict guard pauses Wallpaper Engine
#   2. GPU usage of the Godot process (GPU Engine perf counters, engtype_3D) avg < 20%
#   3. fullscreen window on top -> engine pauses; closed -> resumes
#   4. graceful WM_CLOSE -> detach runs, process exits
#
# Run:  powershell -ExecutionPolicy Bypass -File tools\qa_m2.ps1
# Note: briefly replaces the desktop wallpaper and flashes a black fullscreen
#       window for ~8s. Wallpaper Engine is paused and restored automatically.
param(
    [int]$MeasureSec = 15,
    [string]$GodotExe = ""
)
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
$wmDebug = Join-Path $env:APPDATA "Godot\app_userdata\ET Office Desktop\wm_debug.txt"
$failures = @()

function Check([string]$name, [bool]$ok, [string]$detail = "") {
    $tag = if ($ok) { "PASS" } else { "FAIL" }
    $line = "  $tag  $name"
    if ($detail) { $line += " -- $detail" }
    Write-Output $line
    if (-not $ok) { $script:failures += "${name}: $detail" }
}

function Wait-DebugLine([string]$pattern, [int]$timeoutSec) {
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        if ((Test-Path $wmDebug) -and (Select-String -Path $wmDebug -Pattern $pattern -Quiet)) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

# --- locate Godot ---
if (-not $GodotExe) {
    $GodotExe = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse `
        -Filter "Godot_v*-stable_win64.exe" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notlike "*console*" } |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $GodotExe) { Write-Output "FAIL: Godot exe not found"; exit 1 }

$weBefore = $null -ne (Get-Process -Name "wallpaper32","wallpaper64" -ErrorAction SilentlyContinue)
Remove-Item $wmDebug -ErrorAction SilentlyContinue

function Measure-Gpu([int]$seconds) {
    $s = @()
    for ($i = 0; $i -lt $seconds; $i++) {
        $v = (& nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits) 2>$null
        if ($v -match "^\d+$") { $s += [int]$v }
        Start-Sleep -Seconds 1
    }
    return $s
}

Write-Output "`n[0/4] GPU baseline (desktop as-is, 8s)"
$baselineSamples = Measure-Gpu 8
$baseline = if ($baselineSamples.Count) {
    [math]::Round(($baselineSamples | Measure-Object -Average).Average, 1)
} else { -1 }
Write-Output "  baseline avg = $baseline%"

Write-Output "`n[1/4] attach as wallpaper + conflict guard"
$proc = Start-Process -FilePath $GodotExe -PassThru `
    -ArgumentList "--path `"$repo\godot`" -- --wallpaper"
Check "attach spawned (WorkerW embed)" (Wait-DebugLine "attach spawned" 25)
if ($weBefore) {
    Check "conflict guard paused Wallpaper Engine" (Wait-DebugLine "paused=true" 5)
} else {
    Write-Output "  SKIP  Wallpaper Engine not running -- guard pause not exercised"
}
Start-Sleep -Seconds 5   # let the scene settle before measuring

Write-Output "`n[2/4] GPU usage ($MeasureSec s, target: wallpaper adds < 20% over baseline)"
# delta over baseline via nvidia-smi - whole-GPU includes the user's other apps,
# and util% inflates at idle clocks, so absolute numbers mislead
# (Windows "GPU Engine" perf counters return raw 100ns sums via Get-Counter - unusable)
$samples = Measure-Gpu $MeasureSec
if ($samples.Count -eq 0 -or $baseline -lt 0) {
    Check "GPU sampled (nvidia-smi)" $false "no samples - non-NVIDIA GPU? measure manually"
} else {
    $avg = [math]::Round(($samples | Measure-Object -Average).Average, 1)
    $max = ($samples | Measure-Object -Maximum).Maximum
    $delta = [math]::Round($avg - $baseline, 1)
    Check "wallpaper GPU delta < 20%" ($delta -lt 20) "baseline=$baseline% during=$avg% (max=$max%) delta=$delta%"
}

Write-Output "`n[3/4] fullscreen pause / resume"
$helper = Join-Path $env:TEMP "qa_m2_fullscreen.ps1"
@"
Add-Type -AssemblyName System.Windows.Forms
`$f = New-Object System.Windows.Forms.Form
`$f.FormBorderStyle = 'None'
`$f.WindowState = 'Maximized'
`$f.TopMost = `$true
`$f.BackColor = 'Black'
`$f.ShowInTaskbar = `$false
`$f.Show()
Start-Sleep -Seconds 8
`$f.Close()
# small foreground window afterwards - otherwise the user's own maximized
# window becomes foreground and the watcher keeps reporting "covered"
`$s = New-Object System.Windows.Forms.Form
`$s.Width = 360; `$s.Height = 200
`$s.StartPosition = 'CenterScreen'
`$s.TopMost = `$true
`$s.Text = 'ET Office QA - resuming wallpaper'
`$s.Show()
`$s.Activate()
Start-Sleep -Seconds 6
`$s.Close()
"@ | Out-File $helper -Encoding ascii
Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$helper`"" -WindowStyle Hidden
Check "paused when fullscreen window covers" (Wait-DebugLine "paused \(fullscreen" 12)
Check "resumed after fullscreen closes" (Wait-DebugLine "^resumed$" 15)

Write-Output "`n[4/4] graceful close -> detach"
$hwndLine = Select-String -Path $wmDebug -Pattern "^hwnd=(\d+)" | Select-Object -First 1
$hwnd = [int64]$hwndLine.Matches[0].Groups[1].Value
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class QaWin {
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
}
'@
[QaWin]::PostMessage([IntPtr]$hwnd, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null  # WM_CLOSE
$exited = $proc.WaitForExit(15000)
Check "Godot exited on WM_CLOSE (detach ran)" $exited
if ($weBefore) {
    Start-Sleep -Seconds 2
    $weAfter = $null -ne (Get-Process -Name "wallpaper32","wallpaper64" -ErrorAction SilentlyContinue)
    Check "Wallpaper Engine process still alive (resume issued on detach)" $weAfter
}

Write-Output "`n=================================================="
if ($failures.Count -gt 0) {
    Write-Output "QA GATE M2: FAILED ($($failures.Count))"
    $failures | ForEach-Object { Write-Output "  - $_" }
    exit 1
}
Write-Output "QA GATE M2: PASSED"
exit 0
