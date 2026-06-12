# ET Office Desktop Wallpaper

> 🏢 Cyberpunk Synthwave isometric AI agent office — รันเป็น **live desktop wallpaper** บน Windows
> ขับเคลื่อนด้วย **Ollama + Qwen** (local, ฟรี 100%) + **CrewAI** multi-agent framework

AI Agent ทีมงานเดินทำงาน ประชุม คุยกันเอง อยู่หลัง desktop icon ของคุณ — สั่งงานได้จริง
ผ่าน terminal, จ้าง/ไล่ agent ได้, ให้ทีมสร้าง-แก้ไฟล์ใน workspace ได้โดย**ทุก action
ต้องขออนุญาตคุณก่อนเสมอ** — ข้อมูลไม่ออกนอกเครื่อง ไม่ต้องจ่าย subscription
ใส่ API key เสริม Claude / Gemini / GPT ได้ per-agent

<!-- TODO(M5-10): screenshot Golden Neon + demo GIF ตรงนี้ -->

## ✨ Features

- 🖥️ **Live wallpaper จริง** — ฝังใต้ desktop icon (WorkerW), pause อัตโนมัติเมื่อเปิดเกม
  fullscreen (GPU เป้า <20%), ตรวจจับ Wallpaper Engine/Lively แล้ว pause ให้เอง
- 🤖 **ทีม AI agent** — เดิน 6 โซนออฟฟิศ, สถานะ IDLE/WORKING/THINKING/COLLAB/BREAK/SLEEP,
  คุยกันเองแล้วเสนอ proposal ให้คุณ approve/reject
- ⌨️ **Terminal สั่งงานภาษาไทย** — พิมพ์สั่ง → ระบบ route หา agent ที่เหมาะ → ดูผลสด
- 📁 **Agent Workforce** — ตั้งโฟลเดอร์ workspace แล้วทีมสร้าง/แก้/จัดระเบียบไฟล์,
  รัน PowerShell, ค้นเว็บได้ — sandbox ใต้ workspace + permission gate ทุก action
- 🧑‍💼 **Hire/Fire** — จ้าง agent ใหม่ด้วยไฟล์ role `.md` (หรือให้ AI ร่างให้) / ไล่ออกได้
- 🌆 **บรรยากาศตามเวลาจริง** — Dawn Boot / Cyber Day / Golden Neon / Deep Night
- 🔒 **Privacy first** — ค่า default ทุกอย่างรัน local (Ollama), API key เก็บใน `.env`
  บนเครื่องเท่านั้น

## 📦 ติดตั้ง (ผู้ใช้ทั่วไป)

ความต้องการ: **Windows 10/11** + GPU (แนะนำ VRAM 6GB+ สำหรับ qwen3:8b — น้อยกว่านี้
installer เลือก model เล็กให้อัตโนมัติ)

1. ดาวน์โหลด zip จาก [Releases](../../releases) แล้วแตกไฟล์
2. คลิกขวา `install.ps1` → **Run with PowerShell**
   (ตรวจ/ติดตั้ง Ollama + WebView2 → เลือก model ตาม VRAM → pull → ติดตั้งลง
   `%LOCALAPPDATA%\ET-Office` + สร้าง shortcut)
3. เปิดจาก shortcut **ET Office** — wallpaper + sidebar ขึ้นเอง

ปิดทั้งระบบ: คลิกขวา tray icon ET → ออกจาก ET Office (หรือ Ctrl+C ที่หน้าต่าง launcher)
ถอนการติดตั้ง: ลบโฟลเดอร์ `%LOCALAPPDATA%\ET-Office` + shortcut — ไม่มี registry

## 🚀 เริ่มใช้งาน

| อยากทำ | ทำที่ไหน |
|---|---|
| สั่งงาน agent | หน้าต่าง **ET Terminal** — พิมพ์ภาษาไทยได้เลย |
| ดูสถานะทีม / จ้าง / ไล่ออก | Sidebar → Agent list (ปุ่ม + Hire Agent) |
| ให้ทีมทำงานกับไฟล์จริง | Sidebar → Settings → เลือก **Workspace folder** |
| อนุมัติ action ของทีม | Dialog เด้งใน sidebar — Approve / Deny / อนุมัติทั้ง task |
| สลับ model (local↔cloud) | Sidebar → Settings → model picker ต่อ agent + ใส่ API key |
| เปลี่ยนบรรยากาศ | Sidebar → Settings → Atmosphere picker |

## 🧑‍💻 Dev Setup

```powershell
git clone https://github.com/b2cm92ts5k-alt/et-office-desktop.git
cd et-office-desktop
python -m venv .venv
.venv\Scripts\pip install --prefer-binary -r daemon\requirements.txt
copy daemon\.env.example daemon\.env
ollama pull qwen3:8b
winget install GodotEngine.GodotEngine   # Godot 4.6+
```

รันทั้งระบบ: ดับเบิลคลิก **`et-office.cmd`** (หรือ `--window` ให้ Godot เป็นหน้าต่างปกติ)
รายละเอียด workflow ทั้งหมด (รันแยกส่วน, ถ่ายทำ, จูนภาพ, QA gates, troubleshooting):
**[docs/DEV-RUN-GUIDE.md](docs/DEV-RUN-GUIDE.md)**

Build แจกจ่าย: `powershell -ExecutionPolicy Bypass -File installer\build.ps1`
→ `dist\ET-Office\` (PyInstaller 3 exe + Godot export — ดู guide §5.5)

## Architecture

```
Godot 4 (wallpaper renderer)  ←─ WebSocket ─→  Python FastAPI Daemon  ←─→  CrewAI + Ollama
Sidebar UI (webview2)         ←─ HTTP/WS ───→       (source of truth)        Qwen (local default)
```

| Layer | Stack |
|---|---|
| Renderer | Godot 4.6+ (GDScript) + WorkerW wallpaper embed |
| Daemon | Python 3.12 + FastAPI + WebSocket hub (port 8797) |
| AI | CrewAI + Ollama (qwen3:8b default) / Claude / Gemini / OpenAI optional |
| Sidebar | HTML/CSS/JS + pywebview (WebView2) + pystray |

```
godot/       Godot 4 project — wallpaper renderer (scenes, scripts, shaders, sprites)
daemon/      Python FastAPI server — agents, task router, tools, permissions
sidebar/     Sidebar + Terminal UI (HTML/JS served by daemon) + pywebview host
shell/       launcher.py — เปิด/ปิดทุก process ในคำสั่งเดียว
tools/       wallpaper.ps1 (WorkerW attach/detach) + QA scripts
installer/   install.ps1 (ผู้ใช้) + build.ps1/et-office.spec (build .exe)
```

## ❓ ปัญหาที่เจอบ่อย

| อาการ | ทางแก้ |
|---|---|
| `DAEMON: OFFLINE` ค้างมุมจอ | daemon ยังไม่รัน — เปิดผ่าน shortcut/launcher เสมอ |
| สั่งงานแล้วเงียบ | Ollama ไม่ทำงาน: เปิดแอป Ollama หรือ `ollama serve` |
| wallpaper ไม่ฝัง / จอดำ | ดู `%APPDATA%\Godot\app_userdata\ET Office Desktop\wm_debug.txt` |
| ภาพค้าง fps ตก | มี app fullscreen ทับอยู่ — pause by design |
| เผลอ force kill แล้ว desktop ค้าง | คลิกขวา desktop → Refresh หรือตั้ง wallpaper ใหม่ |

เพิ่มเติม: [docs/DEV-RUN-GUIDE.md §6](docs/DEV-RUN-GUIDE.md)

## Status

🚧 อยู่ระหว่างพัฒนา — ดู [Project Board](https://github.com/users/b2cm92ts5k-alt/projects/1)

## License

[MIT](LICENSE) — โปรเจคนี้เป็นส่วนหนึ่งของ **ETLoLz AI Build** series
