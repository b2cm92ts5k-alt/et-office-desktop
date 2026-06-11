# M2-4 — fullscreen detector: เฝ้าดู foreground window ทุก 1 วิ
# ถ้ามี app fullscreen ทับจอ → เขียน "1" ลง OutFile, ไม่มี → "0" (เขียนเฉพาะตอนเปลี่ยน)
# Godot อ่านไฟล์นี้แล้ว pause/resume rendering — ไว้แทนด้วย daemon detection ภายหลัง
param(
    [Parameter(Mandatory)][string]$OutFile,
    [int]$ParentPid = 0   # ถ้า parent (Godot) ตาย → watcher จบตัวเอง
)

Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class ETFsWatch {
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    public struct RECT { public int L, T, R, B; }
}
"@
Add-Type -AssemblyName System.Windows.Forms

$ignore = @("WorkerW", "Progman", "Shell_TrayWnd", "Windows.UI.Core.CoreWindow", "XamlExplorerHostIslandWindow")
$last = ""
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds

while ($true) {
    if ($ParentPid -ne 0 -and -not (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue)) { break }

    $fg = [ETFsWatch]::GetForegroundWindow()
    $state = "0"
    if ($fg -ne [IntPtr]::Zero) {
        $sb = New-Object System.Text.StringBuilder 256
        [ETFsWatch]::GetClassName($fg, $sb, 256) | Out-Null
        $cls = $sb.ToString()
        $r = New-Object ETFsWatch+RECT
        if ([ETFsWatch]::GetWindowRect($fg, [ref]$r) -and $ignore -notcontains $cls) {
            # ครอบทั้งจอหลัก (เผื่อ 2px สำหรับ borderless ที่ offset เล็กน้อย)
            if ($r.L -le ($bounds.Left + 2) -and $r.T -le ($bounds.Top + 2) -and
                $r.R -ge ($bounds.Right - 2) -and $r.B -ge ($bounds.Bottom - 2)) {
                $state = "1"
            }
        }
    }
    if ($state -ne $last) {
        [System.IO.File]::WriteAllText($OutFile, $state)
        $last = $state
    }
    Start-Sleep -Milliseconds 1000
}
