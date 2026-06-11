# ET Office Desktop — WorkerW wallpaper attach/detach (M2-1 spike → ใช้จริงใน M2-2)
#
# Technique: ส่ง message 0x052C ไปที่ Progman ให้ spawn WorkerW
# แล้ว SetParent window ของเราเข้าไปใต้ desktop icon layer
#
# รองรับ 3 layout ของ Windows:
#   1. Win10/Win11 ส่วนใหญ่ — WorkerW เป็น top-level sibling (หาผ่าน SHELLDLL_DefView)
#   2. Win11 24H2+        — WorkerW เป็น child ของ Progman
#   3. Fallback           — attach เข้า Progman ตรง ๆ
#
# Usage:
#   .\wallpaper.ps1 -Probe                 # ตรวจหา WorkerW อย่างเดียว (รายงาน hwnd)
#   .\wallpaper.ps1 -Attach <hwnd>         # ฝัง window ใต้ desktop icons + ขยายเต็มจอหลัก
#   .\wallpaper.ps1 -Detach <hwnd>         # ถอด window ออก + refresh wallpaper เดิม

param(
    [switch]$Probe,
    [long]$Attach = 0,
    [long]$Detach = 0
)

$ErrorActionPreference = "Stop"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public class ETWallpaper {
    [DllImport("user32.dll", SetLastError = true)]
    public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
    [DllImport("user32.dll", SetLastError = true)]
    public static extern IntPtr FindWindowEx(IntPtr hwndParent, IntPtr hwndChildAfter, string lpszClass, string lpszWindow);
    [DllImport("user32.dll")]
    public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam, uint fuFlags, uint uTimeout, out IntPtr lpdwResult);
    [DllImport("user32.dll", SetLastError = true)]
    public static extern IntPtr SetParent(IntPtr hWndChild, IntPtr hWndNewParent);
    [DllImport("user32.dll")]
    public static extern IntPtr GetParent(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    public static extern bool SystemParametersInfo(uint uiAction, uint uiParam, string pvParam, uint fWinIni);

    private static IntPtr _workerw = IntPtr.Zero;
    public static string FoundVia = "none";

    public static IntPtr GetWallpaperParent() {
        IntPtr progman = FindWindow("Progman", null);
        if (progman == IntPtr.Zero) return IntPtr.Zero;

        // บอก Progman ให้ spawn WorkerW (undocumented but stable since Win7 — ใช้โดย Wallpaper Engine)
        IntPtr result;
        SendMessageTimeout(progman, 0x052C, new IntPtr(0xD), new IntPtr(0x1), 0x0, 1000, out result);

        // Layout 1: WorkerW = top-level sibling ถัดจาก window ที่มี SHELLDLL_DefView
        _workerw = IntPtr.Zero;
        EnumWindows(delegate(IntPtr top, IntPtr lp) {
            IntPtr shellView = FindWindowEx(top, IntPtr.Zero, "SHELLDLL_DefView", null);
            if (shellView != IntPtr.Zero) {
                IntPtr w = FindWindowEx(IntPtr.Zero, top, "WorkerW", null);
                if (w != IntPtr.Zero) { _workerw = w; FoundVia = "sibling-after-SHELLDLL_DefView"; }
            }
            return true;
        }, IntPtr.Zero);

        // Layout 2 (Win11 24H2+): WorkerW เป็น child ของ Progman
        if (_workerw == IntPtr.Zero) {
            _workerw = FindWindowEx(progman, IntPtr.Zero, "WorkerW", null);
            if (_workerw != IntPtr.Zero) FoundVia = "child-of-Progman";
        }

        // Layout 3: fallback ใช้ Progman เอง (SHELLDLL_DefView อยู่ใต้ Progman โดยตรง)
        if (_workerw == IntPtr.Zero) {
            _workerw = progman;
            FoundVia = "Progman-fallback";
        }
        return _workerw;
    }
}
"@

Add-Type -AssemblyName System.Windows.Forms

function Get-PrimaryBounds {
    return [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
}

if ($Probe) {
    $w = [ETWallpaper]::GetWallpaperParent()
    Write-Output ("WorkerW hwnd : " + $w)
    Write-Output ("Found via    : " + [ETWallpaper]::FoundVia)
    if ($w -eq [IntPtr]::Zero) { Write-Output "RESULT: FAIL — no wallpaper parent found"; exit 1 }
    Write-Output "RESULT: OK"
    exit 0
}

if ($Attach -ne 0) {
    $child = [IntPtr]$Attach
    $w = [ETWallpaper]::GetWallpaperParent()
    if ($w -eq [IntPtr]::Zero) { Write-Output "FAIL: WorkerW not found"; exit 1 }

    $prev = [ETWallpaper]::SetParent($child, $w)
    if ($prev -eq [IntPtr]::Zero) { Write-Output "FAIL: SetParent returned 0 (error $([Runtime.InteropServices.Marshal]::GetLastWin32Error()))"; exit 1 }

    # หลัง SetParent พิกัดเป็น relative กับ WorkerW — จัดเต็มจอหลัก
    $b = Get-PrimaryBounds
    [ETWallpaper]::MoveWindow($child, 0, 0, $b.Width, $b.Height, $true) | Out-Null

    Write-Output ("ATTACHED: hwnd " + $child + " -> WorkerW " + $w + " (via " + [ETWallpaper]::FoundVia + ")")
    Write-Output ("VERIFY  : GetParent = " + [ETWallpaper]::GetParent($child))
    exit 0
}

if ($Detach -ne 0) {
    $child = [IntPtr]$Detach
    [ETWallpaper]::SetParent($child, [IntPtr]::Zero) | Out-Null

    # Refresh wallpaper เดิมจาก registry กัน desktop ค้างภาพ
    $wp = (Get-ItemProperty "HKCU:\Control Panel\Desktop" -Name WallPaper -ErrorAction SilentlyContinue).WallPaper
    if ($wp) { [ETWallpaper]::SystemParametersInfo(0x0014, 0, $wp, 0x01) | Out-Null }  # SPI_SETDESKWALLPAPER

    Write-Output ("DETACHED: hwnd " + $child + " — wallpaper refreshed")
    exit 0
}

Write-Output "Usage: wallpaper.ps1 -Probe | -Attach <hwnd> | -Detach <hwnd>"
exit 1
