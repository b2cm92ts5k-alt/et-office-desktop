# ET Office — คู่มือรันเพื่อตรวจสอบ & ถ่ายทำระหว่างพัฒนา

> สำหรับ dev/QA/ถ่ายทำ ก่อนที่ launcher จริง (M5-1) จะเสร็จ

⚠️ **ทุกคำสั่งเป็น PowerShell (ห้ามใช้ Command Prompt/cmd — syntax `&` กับ `$ตัวแปร` ใช้กันคนละแบบ)
และต้อง `cd` มาที่ root ของ repo ก่อนเสมอ** — เปิด PowerShell แล้วเริ่มด้วย:

```powershell
cd "D:\Project\ETLOLZ\Project in content\ET office desktop wallpaper\et-office-desktop"
```

💡 **ทางลัดไม่ต้องพิมพ์เลย — ดับเบิลคลิกไฟล์ใน root repo:**

| ไฟล์ | ทำอะไร |
|---|---|
| `et-office.cmd` | **เปิดครบทุกตัวในคลิกเดียว** (daemon → Godot wallpaper → sidebar) — launcher M5-1 · args: `--window` (Godot เป็น window), `--no-godot`, `--no-sidebar` |
| `dev-godot.cmd` | เปิด Godot โหมด window ตัวเดียว — ส่ง arg ได้ เช่น `dev-godot.cmd --wallpaper` |
| `dev-sidebar.cmd` | เปิด sidebar ตัวเดียว (daemon ต้องรันก่อน) |

ปิดทั้งระบบเมื่อเปิดผ่าน launcher: **Ctrl+C ที่หน้าต่าง launcher / ออกจาก tray ET /
ปิดหน้าต่าง Godot** — ตัวใดตัวหนึ่งจบ launcher จะปิดที่เหลือให้ถูกลำดับเอง
(Godot โดน WM_CLOSE เสมอ → detach + คืน wallpaper เดิม)

## 0. ของที่ต้องมี

| ตัว | ที่อยู่ / คำสั่งเช็ค |
|---|---|
| Godot 4.6 | `Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter "Godot_v*-stable_win64.exe"` |
| Python venv | `.venv\` (มีอยู่แล้ว — ถ้าไม่มีดู Quick Start ใน README) |
| Ollama | `ollama list` ต้องเห็น `qwen3:8b` (ไม่จำเป็นถ้าแค่ตรวจภาพ) |

ตั้งตัวแปรไว้ใช้ทั้ง session (แก้ path ตามเครื่อง):

```powershell
$godot = (Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse `
    -Filter "Godot_v*-stable_win64.exe" | Select-Object -First 1).FullName
```

---

## 1. โหมดตรวจภาพเร็ว (ไม่ต้องมี daemon)

ใช้เช็คเลย์เอาต์ / shader / camera — Godot รันเป็น window ปกติ มุมขวาบนจะขึ้น
`DAEMON: OFFLINE` ซึ่งไม่เป็นไร ฉาก + shader ทำงานครบ (ยกเว้น agent ไม่ spawn)

```powershell
& $godot --path godot
```

ถ่าย screenshot ทั้งจอเก็บผล:

```powershell
powershell -ExecutionPolicy Bypass -File tools\screenshot.ps1 -OutPath out.png
```

หรือเปิดผ่าน editor (แก้ค่า shader สด ๆ ได้ใน Inspector):

```powershell
& $godot --editor --path godot
```

## 2. โหมดครบวงจร (agent เดิน + ทำงานจริง)

ทางลัดคำสั่งเดียว (M5-1): `.venv\Scripts\python.exe shell\launcher.py --window`
(หรือ `et-office.cmd --window`) — เปิดครบ 3 ตัว จัดลำดับ + รอ /health ให้เอง

หรือเปิดเองทีละตัวด้วย 3 terminal (debug แยกส่วน):

```powershell
# terminal 1 — daemon (พอร์ต 8797)
.venv\Scripts\python.exe -m uvicorn daemon.main:app --port 8797
# (ทางลัด: et-office.cmd ทำคำสั่งเดียวกัน)

# terminal 2 — Godot
& $godot --path godot

# terminal 3 — sidebar (ถ้าต้องการ panel)
.venv\Scripts\python.exe sidebar\host.py
```

ลำดับ: daemon ก่อนเสมอ → Godot ต่อ WS อัตโนมัติ (`DAEMON: ONLINE` สีเขียว)
ถ้าเปิด daemon ทีหลัง Godot ก็ reconnect เองภายในไม่กี่วินาที

## 3. โหมด wallpaper จริง (ฝังใต้ desktop icon)

```powershell
& $godot --path godot -- --wallpaper
```

- ปิด: ส่ง WM_CLOSE (ปิดจาก taskbar / `Stop-Process -Name Godot*`) → detach + คืน Wallpaper Engine อัตโนมัติ
- มี Wallpaper Engine / Lively รันอยู่ → conflict guard (M2-14) pause ให้เองและแจ้งผ่าน sidebar
- debug log เขียนลง `%APPDATA%\Godot\app_userdata\ET Office Desktop\wm_debug.txt`
- ⚠️ มี **fullscreen app ทับจอ → engine pause เอง** (M2-4, fps ตกเหลือ 2) — สำคัญตอนถ่ายทำ ดูข้อ 4

---

## 4. ถ่ายทำ / เก็บ footage

### 4.1 ล็อกบรรยากาศ (สวยสุด: Golden Neon — ตาม Design doc และ M5-10)

ผ่าน sidebar: Settings → Atmosphere picker (M4-10) หรือยิงตรง (daemon ต้องรัน):

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8797/event -ContentType "application/json" `
  -Body '{"type": "atmosphere.set", "data": {"mode": "golden"}}'
# mode: dawn | day | golden | night | auto (กลับไปตามนาฬิกาจริง)
```

### 4.2 ทำให้ agent มีอะไรทำ (เดิน / WORKING / speech bubble)

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8797/task -ContentType "application/json" `
  -Body '{"message": "สรุปสั้น ๆ: ทำไม pixel art เหมาะกับ desktop wallpaper"}'
```

- agent จะ THINKING (hologram bubble ลอย) → WORKING (aura pulse) → ตอบเสร็จมี ticker
- ปล่อยไว้เฉย ๆ ~5 นาที social loop (M3-9) จะให้ agent เดินไปคุยกันเอง — footage ธรรมชาติสุด

### 4.3 อัดวิดีโอ

**วิธีแนะนำ — Godot Movie Maker (เฟรมนิ่ง 30fps ไม่มีหลุด ไม่ต้องใช้ OBS):**

```powershell
& $godot --path godot --write-movie demo.avi --fixed-fps 30
```

ปิดหน้าต่างเมื่อพอ — ได้ `godot\demo.avi` (MJPEG) ไปตัดต่อได้เลย
(นามสกุล `.png` จะได้ image sequence แทน)

**ถ้าอัดทั้ง desktop ด้วย OBS ในโหมด wallpaper:**
- ใช้ **Display Capture** — อย่ารัน game/app fullscreen ระหว่างอัด ไม่งั้น wallpaper pause เอง (M2-4)
- OBS เองไม่ trigger pause ตราบใดที่ไม่มี window fullscreen ทับจอหลัก

### 4.4 จุดจูนภาพ (แก้ที่เดียวจบ)

| อยากปรับ | ที่ไหน |
|---|---|
| ระยะ camera / ขอบข้างจอ | `camera_zoom` ใน `scripts/camera_rig.gd` (default 1.25) หรือ Inspector ที่ node `Camera` |
| ความชัด scanline/vignette CRT | uniforms ใน `ShaderMaterial_crt` ที่ node `CrtLayer/CrtOverlay` (`line_alpha`, `vignette_alpha`) |
| ความฟุ้งป้าย neon | `spread`, `intensity` ใน `shaders/neon_glow.gdshader` |
| แสงสะท้อนพื้น | `reflect_strength`, `sweep_strength` ใน `shaders/floor_reflect.gdshader` |
| โทนสีตามเวลา | `MODES` ใน `scripts/atmosphere.gd` |
| ความถี่ป้ายกระพริบ | `BLINK_CHANCE` ใน `scripts/neon_signs.gd` |

แก้ `.gdshader` แล้วรันใหม่ได้เลย ไม่ต้อง re-import / ถ้าเปิดผ่าน `--editor` แก้ uniform เห็นผลสด

---

## 5. QA gates (รันก่อน merge งานใหญ่)

```powershell
powershell -ExecutionPolicy Bypass -File tools\qa_m2.ps1   # wallpaper embed + GPU <20% + fullscreen pause
.venv\Scripts\python.exe tools\qa_m3.py                    # agent เดิน/status sync (daemon ต้องรัน)
.venv\Scripts\python.exe tools\qa_m4.py                    # sidebar (daemon ต้องรัน)
.venv\Scripts\python.exe tools\qa_m6.py                    # agent workforce: hire/fire + workspace tools + permission gate (daemon + Ollama ต้องรัน)
```

⚠️ `qa_m2.ps1` จะสลับ wallpaper จริง + เด้งหน้าต่างดำ ~8 วิ — อย่ารันระหว่างอัดวิดีโอ

## 6. Troubleshooting

| อาการ | เช็ค |
|---|---|
| `DAEMON: OFFLINE` ค้าง | daemon รันอยู่ไหม: `Invoke-RestMethod http://localhost:8797/health` |
| task ส่งแล้วเงียบ | Ollama รันไหม: `ollama list` / ดู log terminal daemon |
| wallpaper ไม่ฝัง | อ่าน `wm_debug.txt` (path ข้อ 3) — ดูบรรทัด `attach spawned` / `script not found` |
| ภาพค้าง/fps ตก | มี fullscreen app ทับอยู่หรือเปล่า (pause by design) |
| hologram bubble ไม่ขึ้น | ต้องมี daemon + agent อยู่ในสถานะ THINKING หรือมี event ให้พูด (ข้อ 4.2) |

## 7. ปิดให้หมด

ทีละตัว (นุ่มนวลสุด):

1. **Sidebar** — คลิกขวา tray icon ET → "ออกจาก ET Office"
2. **Godot** — โหมด window กด X / Alt+F4 — โหมด wallpaper ไม่มี X ให้กด ใช้:
   ```powershell
   Get-Process Godot* -ErrorAction SilentlyContinue | ForEach-Object { $_.CloseMainWindow() }
   ```
   ⚠️ ห้าม `Stop-Process -Force` ตอนเป็น wallpaper — WM_CLOSE คือตัว trigger detach +
   คืน wallpaper เดิม + คืน Wallpaper Engine (M2-14)
3. **Daemon** — Ctrl+C ใน terminal ที่รัน uvicorn

หรือปิดทั้งหมดคำสั่งเดียว:

```powershell
Get-Process Godot* -ErrorAction SilentlyContinue | ForEach-Object { $_.CloseMainWindow() }
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'uvicorn daemon|sidebar\\host' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -Confirm:$false }
```

- `fullscreen-watch.ps1` เบื้องหลังปิดตัวเองตาม Godot — ไม่ต้องจัดการ
- ถ้าเผลอ force kill Godot ตอนเป็น wallpaper แล้วจอค้าง: คลิกขวา desktop → Refresh
  หรือตั้ง wallpaper ใหม่ใน Settings → Personalization
