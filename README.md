# ET Office Desktop Wallpaper

> 🏢 Cyberpunk Synthwave isometric **AI agent office** — รันเป็น **live desktop wallpaper** บน Windows
> ทีม AI ทำงานเป็นทีมจริง (Sub-Agent): หัวหน้าแตกงาน → มอบหมายลูกทีม → รวมผล
>
> 🟢 **Local First** — ทำงานได้ **100% ฟรีบนเครื่องคุณ** ด้วย **Ollama + Qwen** (ไม่ต้องต่อเน็ต ไม่ต้องจ่าย
> ไม่ส่งข้อมูลออก) · cloud (Claude/Gemini/GPT/Grok/DeepSeek/OpenRouter/GitHub Models) เป็น **ของเสริม opt-in**
> เฉพาะ agent ที่อยากได้คุณภาพ/ความเร็วสูงขึ้น

**เวอร์ชันปัจจุบัน: `v0.21.0`** — M21 ทำงานต่อ · M22 agent มีชีวิต/คุยเป็นกลุ่ม · M23 multi-domain · M24 cloud reliability

AI Agent ทีมงานเดินทำงาน ประชุม คุยกันเอง อยู่หลัง desktop icon ของคุณ — **สั่งงานได้จริง**:
สั่งหนึ่งคำสั่ง → **Producer แตกงานเป็นขั้น แล้วกระจายให้ specialist ทำต่อกัน** → สร้าง/แก้ไฟล์,
รันคำสั่ง, ค้นเว็บ, **สร้างภาพ** ใน workspace ของคุณ โดย**ทุก action ต้องขออนุญาตคุณก่อนเสมอ** —
ข้อมูลไม่ออกนอกเครื่อง ไม่ต้องจ่าย subscription แต่คุณภาพของผลงานที่ได้ขึ้นอยู่กับความสามารถของ Models ที่เลือกใช้ด้วย

<!-- TODO: screenshot Golden Neon + demo GIF -->

---

## ✨ Features

- 🟢 **Local First (ฟรี 100%)** — default รันด้วย Ollama + Qwen บนเครื่องคุณ ไม่ต้องมี key/เน็ต/ค่าใช้จ่าย
- 🤝 **ทำงานเป็นทีมจริง (Sub-Agent / Orchestrator)** — สั่งงานทั่วไป → Producer แตกงานเป็น subtask
  อัตโนมัติ → มอบหมายให้ specialist ตาม role → รวมผลเป็นคำตอบเดียว (ดู agent สว่างทีละตัวในออฟฟิศ)
- ✅ **รายงานตามจริง (ไม่หลอกว่าเสร็จ)** — กด REJECT = หยุดจริง + ข้ามขั้นที่พึ่งกัน · งานที่ควรได้ไฟล์
  (ภาพ/เสียง/โค้ด) แต่ไม่มี = สรุปว่า "ยังไม่ครบ" ไม่ปั้นว่าเสร็จ
- 🎨 **สร้างภาพได้ (ET Artist)** — tool `generate_image` (Nano Banana / Imagen / gpt-image / DALL·E) —
  **เลือก image model แยกจากสมอง agent ได้**
- 🧠 **Skills** — สูตรทำงานทีละขั้นที่ inject ให้ agent อัตโนมัติเมื่องานตรง (วิจัย/เขียนโค้ด/วางแผน/
  จัดไฟล์/ทำเกมเล็ก) — ทำให้ model local เก่งขึ้นโดยไม่ต้องพึ่ง cloud
- 🎯 **Role Tool Presets** — จ้าง agent ตาม role → tool ที่ควรใช้ถูกติ๊กให้อัตโนมัติ (ไม่ต้องนั่งติ๊กเอง)
- 🖥️ **Live wallpaper จริง** — ฝังใต้ desktop icon (WorkerW), pause อัตโนมัติเมื่อเปิดเกม fullscreen
- ⌨️ **Terminal สั่งงานภาษาไทย** — สั่งทีม / เลือกผู้รับตรง / คุยเล่นกับ agent ได้
- 📁 **Agent Workforce + Tools** — ไฟล์ (สร้าง/อ่าน/แก้/ย้าย/ลบ), PowerShell, **web_search**, fetch_url,
  generate_image, Git, GitHub issues — sandbox ใต้ workspace + **permission gate ทุก action**
- ☁️ **Cloud per-agent (optional)** — 1 API key เลือก model ได้ **ครบทุกตัวที่ key เปิดให้** (ไม่ฟิกแค่ไม่กี่ตัว);
  รองรับ **7 เจ้า**: Claude · Gemini · OpenAI · Grok · DeepSeek · **OpenRouter** · **GitHub Models** —
  key เก็บ **เข้ารหัส DPAPI** ในเครื่อง
- 🧑‍💼 **Hire/Fire + Roles** — จ้าง agent ด้วยไฟล์ role `.md` (หรือให้ AI ร่าง) / ไล่ออกได้
- 🌆 **บรรยากาศตามเวลาจริง** — Dawn Boot / Cyber Day / Golden Neon / Deep Night
- 🔒 **Privacy first** — secret อยู่แค่ในเครื่อง ไม่ log/ไม่ส่งออก

---

## 📦 ติดตั้ง (ผู้ใช้ทั่วไป)

ความต้องการ: **Windows 10/11** + GPU (แนะนำ VRAM 6GB+ สำหรับ qwen3:8b — น้อยกว่านี้ installer
เลือก model เล็กให้อัตโนมัติ) · **ไม่ต้องมี API key** ก็ใช้งานได้เต็มที่ (local)

1. ดาวน์โหลด zip จาก [Releases](../../releases) แล้วแตกไฟล์
2. คลิกขวา `install.ps1` → **Run with PowerShell**
   (ตรวจ/ติดตั้ง Ollama + WebView2 → เลือก model ตาม VRAM → pull → ติดตั้งลง `%LOCALAPPDATA%\ET-Office`)
3. เปิดจาก shortcut **ET Office** — wallpaper + sidebar ขึ้นเอง

ปิดทั้งระบบ: คลิกขวา tray icon ET → ออกจาก ET Office · ถอนการติดตั้ง: ลบโฟลเดอร์ `%LOCALAPPDATA%\ET-Office`
+ shortcut (ไม่มี registry)

---

## 📖 คู่มือการใช้งาน (Manual)

### 1) สั่งงานทีม — Sub-Agent / Orchestrator
หัวใจของ ET Office: พิมพ์คำสั่งใน **ET Terminal** (ไม่ต้องเลือกผู้รับ) ระบบจะ:
1. **Producer แตกงาน** เป็นขั้น ๆ + เลือก specialist ที่เหมาะ (เห็นใน feed: `👥 แตกงานเป็น N ขั้น`)
2. **ลูกทีมลงมือทีละคน** — แต่ละขั้นเห็นเป้าหมายเดิม + งานที่คนก่อนทำ (ไม่ทำซ้ำ/หลงโจทย์)
3. **รวมผลเป็นคำตอบเดียว** + สรุปตามจริงว่าได้/ขาดอะไร

> 💡 ตัวอย่าง: *"ค้นข้อมูลคู่แข่ง 3 เจ้า แล้วทำเอกสารสรุป + ร่างแผนการตลาด"* → Researcher ค้น →
> Producer สรุป → ทีมร่างแผน

**สั่งคนเดียว / คุยเล่น:** ในเทอร์มินอลเลือกผู้รับ (agent เจาะจง) = ทำเดี่ยวไม่แตกงาน · ปุ่ม 💬 คุยเล่น
= สนทนาเฉย ๆ (ถ้าขอให้ทำงานจริงจะ escalate เป็น task ให้)

### 2) Workspace + Tools + Permission
ก่อนทีมทำงานกับไฟล์ได้ ต้องตั้ง **Workspace folder** ก่อน (Sidebar → Settings):
- agent ทำได้เฉพาะ **ใต้โฟลเดอร์ workspace** (sandbox — ออกนอกไม่ได้)
- **ทุก action เด้ง dialog ขออนุญาต** → Approve / Deny / "อนุมัติที่เหลือทั้ง task นี้" · **Deny = ขั้นนั้นยกเลิกจริง**
- Tools: `list_dir` `read_file` `write_file` `mkdir` `move` `delete` `powershell` `web_search`
  `fetch_url` `generate_image` `git_*` `gh_*`
- จำกัด tool ต่อ agent ได้ที่ ⚙ → ติ๊กเฉพาะที่อนุญาต (**ไม่ติ๊ก = อนุญาตทุก tool**) · ปุ่ม
  **🎯 ใช้ tool ตาม role** ติ๊กชุดที่เหมาะให้อัตโนมัติ

### 3) Skills (สูตรทำงาน)
Sidebar → Settings → **SKILLS** — เปิด/ปิด/ดูสูตรได้ สกิลจะ inject ให้ agent อัตโนมัติเมื่องานตรงคีย์เวิร์ด
(เช่น "ค้นข้อมูล...รายงาน" → สูตร research-and-report) สกิลในตัว: research-and-report, build-feature,
write-plan, organize-files, small-game-team · เพิ่มเองได้ที่ `daemon/data/skills/*.md`

### 4) Cloud API Keys + เลือก model ต่อ agent (optional)
- Sidebar → Settings → **API KEYS** → เลือก provider (Claude/Gemini/OpenAI/Grok/DeepSeek/**OpenRouter**/
  **GitHub Models**) + วาง key → ADD (validate + เก็บ **เข้ารหัส DPAPI**) · ใส่ใน `.env` ก็ได้
- **1 key เห็น model ครบทุกตัวที่ key เปิดให้** (ดึงจริงจาก provider) — กดปุ่ม 🔄 รีเฟรชเมื่อ provider ออกรุ่นใหม่
- ที่ ⚙ ของ agent: เลือก **Model** (แสดงชื่อ model อย่างเดียว) → เลือก **Key/บัญชี**
- ⚠️ **ใช้ได้เฉพาะ developer API key** — ค่าสมาชิกแชต (ChatGPT Plus / Gemini Advanced / Claude Pro /
  SuperGrok) เอามายิงจากแอปไม่ได้ (ผิด ToS)
- web_search: ฟรี (DuckDuckGo) — ใส่ `BRAVE_API_KEY` ถ้าอยากแม่นขึ้น

### 5) เลือก model ให้เหมาะกับหน้าที่ของ agent 🎯
**หลัก Local First:** เริ่มจาก local (ฟรี) ทุกตัวก่อน แล้ว**อัปเฉพาะ agent ที่ต้องการคุณภาพ/ความเร็ว**เป็น cloud

| Agent / หน้าที่ | แนะนำ |
|---|---|
| **Producer** (วางแผน/แตกงาน) | งานหนักสุดทางความคิด — local `qwen3:8b`+ พอได้งานง่าย; งานซับซ้อนอยากแม่น → cloud (Claude Sonnet / GPT / Gemini Pro) |
| **Developer / Coder** | `qwen2.5-coder` (local) หรือ cloud coding model |
| **Researcher** | local + `web_search` (ฟรี) หรือ Gemini Flash (เร็ว+ถูก) |
| **Designer / Writer** | local ทั่วไปพอ; อยากได้คุณภาพภาษา → cloud |
| **Artist (ภาพ)** | สมองเป็น local/cloud ก็ได้ + ตั้ง **image model** แยก (Nano Banana ฟรี / Imagen / gpt-image) |
| **Tester / Sound Designer** | local พอ (Sound เขียนสเปคเสียง — ยังไม่มีโมเดลสร้างไฟล์เสียงในตัว) |

> 💡 Cloud ฟรีแบบมีโควต้า: **Gemini** (Google AI Studio) + **GitHub Models** ใช้ฟรีมีลิมิตต่อวัน ·
> Claude/OpenAI/Grok/DeepSeek = จ่ายตามใช้ · OpenRouter = มีทั้งฟรีและจ่าย

### 6) Model Manager (local)
Sidebar → Settings → **LOCAL MODELS** — ติดตั้ง/สลับ local model (ผ่าน Ollama) · กฎ: ใช้ local
**ตัวเดียวทั้งทีม** ในแต่ละครั้ง (กันโหลดหลายตัวจน VRAM ล้น) — สลับได้ผ่านปุ่ม "สลับมาใช้"

### 7) Hire / Fire / Roles
Sidebar → Agent list → **+ Hire** — แนบไฟล์ role `.md` (upload หรือเขียนในแอป) หรือให้ AI ร่างให้ →
ผูก system prompt + keywords (tool ถูกติ๊กตาม role ให้อัตโนมัติ) · ไล่ออกด้วยปุ่ม ✕ (CEO ไล่ไม่ได้)

### 8) GitHub / MCP (optional)
- **GitHub:** Settings → ผูก token (fine-grained) + repo → agent ใช้ `gh_*` (issue) + `git_*` (commit/push)
- **MCP:** Settings → เพิ่ม MCP server (stdio) → tool ของ server โผล่ให้ agent ใช้ (`mcp__srv__tool`)

### 9) บรรยากาศ / wallpaper
Settings → Atmosphere picker (Dawn/Day/Golden/Night) · wallpaper แสดงบนจอหลักเท่านั้น · pause เองเมื่อ
มีแอป fullscreen

---

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
รายละเอียด workflow (รันแยกส่วน, จูนภาพ, QA gates, troubleshooting): **[docs/DEV-RUN-GUIDE.md](docs/DEV-RUN-GUIDE.md)**

QA แต่ละ milestone: `python daemon/qa_m16.py` … `qa_m20.py` · Build แจกจ่าย: `installer\build.ps1` → `dist\ET-Office\`
ดีไซน์รายฟีเจอร์: `docs/M16-DESIGN.md` … `M22-DESIGN.md`

---

## Architecture

```
Godot 4 (wallpaper renderer)  ←─ WebSocket ─→  Python FastAPI Daemon  ←─→  CrewAI + Ollama / Cloud
Sidebar UI (webview2)         ←─ HTTP/WS ───→       (source of truth)        Qwen (local default)
```

| Layer | Stack |
|---|---|
| Renderer | Godot 4.6+ (GDScript) + WorkerW wallpaper embed |
| Daemon | Python 3.12 + FastAPI + WebSocket hub (port 8797) |
| AI | CrewAI + Ollama (qwen3:8b default) · cloud optional: 7 providers (dynamic per-key model list) |
| Orchestration | Sub-Agent (decompose→dispatch→synthesize) + shared context + per-kind verify + Skills + permission gate |
| Sidebar | HTML/CSS/JS + pywebview (WebView2) + pystray |

```
godot/       Godot 4 project — wallpaper renderer (scenes, scripts, shaders, sprites)
daemon/      Python FastAPI server — agents, orchestrator, task router, skills, tools, accounts
  ├─ services/   orchestrator_service · task_router · skill_service · account_store (DPAPI) · ...
  ├─ adapters/   llm_adapter (provider registry) · image_adapter (generate_image) · mcp_client
  └─ data/       skills/*.md · agents.json · accounts (encrypted)
sidebar/     Sidebar + Terminal UI (HTML/JS) + pywebview host
shell/       launcher.py — เปิด/ปิดทุก process ในคำสั่งเดียว
tools/       wallpaper.ps1 (WorkerW)
installer/   install.ps1 (ผู้ใช้) + build.ps1 (build .exe)
```

---

## ❓ ปัญหาที่เจอบ่อย

| อาการ | ทางแก้ |
|---|---|
| `DAEMON: OFFLINE` ค้างมุมจอ | daemon ยังไม่รัน — เปิดผ่าน shortcut/launcher เสมอ |
| สั่งงานแล้วเงียบ | Ollama ไม่ทำงาน: เปิดแอป Ollama หรือ `ollama serve` |
| agent ตอบเป็นแชทเฉย ไม่แตะไฟล์ | ยังไม่ตั้ง **Workspace folder** ใน Settings |
| cloud คืน 429 / 403 | key หมดโควต้า/ถูกระงับ — สลับ key/provider หรือใช้ local (qwen3:8b ฟรี) |
| แตกงานเพี้ยน/ไม่แตก | ตั้ง Producer ใช้ cloud (Claude Sonnet) จะแม่นกว่า local |
| wallpaper ไม่ฝัง / จอดำ | ดู `%APPDATA%\Godot\app_userdata\ET Office Desktop\wm_debug.txt` |

เพิ่มเติม: [docs/DEV-RUN-GUIDE.md §6](docs/DEV-RUN-GUIDE.md)

---

## 📜 License

**[PolyForm Noncommercial License 1.0.0](LICENSE)** + Additional Terms — สรุป:

- ✅ **ใช้ฟรี + ปรับแต่ง + แจกจ่ายต่อ** (แบบไม่เชิงพาณิชย์) ได้
- ❌ **ห้ามนำตัวโปรแกรม ET Office ไปใช้เชิงพาณิชย์** (ขาย/ให้เช่า/เสนอเป็นสินค้า-บริการ — ทั้งตัวเดิม
  และตัวดัดแปลง)
- ✅ **ผลงานที่คุณสร้างจากการใช้ ET Office เป็นของคุณ 100% — เอาไปขาย/ใช้เชิงพาณิชย์ได้เต็มที่**
  (ข้อจำกัดไม่เชิงพาณิชย์บังคับกับตัวโปรแกรมเท่านั้น ไม่เกี่ยวกับสิ่งที่คุณทำด้วยมัน)

โปรเจคนี้เป็นส่วนหนึ่งของ **ETLoLz AI Build** series
