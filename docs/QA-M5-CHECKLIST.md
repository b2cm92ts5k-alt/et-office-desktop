# QA Gate M5-8 — Clean Install Checklist (Win10 + Win11)

> ด่านสุดท้ายก่อนปล่อย **v1.0** — ลงบนเครื่องที่ **ไม่เคยมี dev tools** (ไม่มี Python,
> ไม่มี Ollama, ไม่มี WebView2, ไม่มี Godot) ทั้ง **Windows 10** และ **Windows 11**
> เพราะพฤติกรรม WorkerW (wallpaper embed) ต่างกันระหว่างสองเวอร์ชัน
>
> รันพรีไฟลต์อัตโนมัติก่อนเสมอ: `python tools/qa_m5.py` (ต้องผ่านครบ → ค่อยมาทำตารางนี้)
> เครื่องเปล่าไม่มี Python ก็ข้ามพรีไฟลต์ได้ — ทำบนเครื่อง build แทน

## 0) เตรียมก่อนทดสอบ
- [ ] `installer/build.ps1` สร้าง `dist/ET-Office/` ครบ (ET-Office.exe, et-office-daemon.exe, et-office-sidebar.exe)
- [ ] zip `dist/ET-Office/` + `installer/install.ps1` เป็นไฟล์ release เดียว
- [ ] เครื่องทดสอบเป็น clean install จริง (VM snapshot สดยิ่งดี — ย้อนกลับได้)
- [ ] จด GPU / VRAM ของเครื่องทดสอบไว้ (คาดเดา model ที่จะถูก pull)

---

## A) Windows 10

### ติดตั้ง
- [ ] แตก zip → คลิกขวา `install.ps1` → Run with PowerShell (หรือ `powershell -ExecutionPolicy Bypass -File install.ps1`)
- [ ] WebView2: ตรวจไม่เจอ → ดาวน์โหลด+ติดตั้งเงียบสำเร็จ
- [ ] Ollama: ตรวจไม่เจอ → ติดตั้งผ่าน winget/ตัวติดตั้งตรงสำเร็จ + ปลุก serve ขึ้น
- [ ] VRAM detect ถูกต้อง → pull model ตรงกับ MODEL_MAP (<4GB qwen2.5:1.5b / <16GB qwen3:8b / 16GB+ qwen3:32b)
- [ ] คัดลอกลง `%LOCALAPPDATA%\ET-Office` + สร้าง shortcut **Desktop** และ **Start Menu**
- [ ] **A-8:** shortcut + ทั้ง 3 .exe โชว์ไอคอน ET (ไม่ใช่ไอคอน default ของ Windows)

### เปิดใช้งานครั้งแรก
- [ ] เปิดจาก shortcut "ET Office" → console launcher ขึ้น log ครบ (daemon → Godot → sidebar)
- [ ] **Wallpaper embed:** office scene แสดงใต้ไอคอน desktop, ไอคอน desktop ยังคลิกได้ปกติ
- [ ] **M8 onboarding:** หน้าต่างแรกให้สร้างตัวละคร CEO → สร้างแล้วตัวละครโผล่ใน office
- [ ] System tray มีไอคอน ET (A-8) → คลิกซ้าย toggle sidebar, คลิกขวาเมนูครบ
- [ ] สั่ง task ภาษาไทยใน terminal → Qwen ตอบ + agent เดินไปทำงาน เปลี่ยน status

### M5-5 — error / empty / loading states (สำคัญสำหรับเครื่องเปล่า)
- [ ] เปิด sidebar ก่อน daemon พร้อม → เห็น overlay **"กำลังเชื่อมต่อ…"** (สปินเนอร์ฟ้า)
- [ ] ปิด daemon/launcher ทิ้งระหว่าง sidebar เปิด → overlay **"DAEMON ไม่ทำงาน"** (สปินเนอร์ส้ม) + ข้อความให้เปิด ET-Office.exe
- [ ] เปิด daemon กลับ → overlay หายเอง เชื่อมใหม่อัตโนมัติ (ไม่ต้องรีโหลด)
- [ ] ปิด Ollama แล้วเปิด sidebar → banner **"⚠ Ollama ไม่ได้รัน"** ขึ้นใต้หัวข้อ
- [ ] เปิด Ollama กลับ (หรือลง model แรกเสร็จ) → banner หาย
- [ ] ไล่ออก agent จนเหลือแต่ CEO → empty-state รายชื่อแสดงข้อความชวนกด HIRE (ไม่ใช่ช่องว่าง)

### ปิด + ถอนการติดตั้ง
- [ ] ปิดจาก tray → wallpaper เดิมคืน, ไม่มี process ค้าง (Task Manager: et-office-*, Godot, daemon หายหมด)
- [ ] ลบโฟลเดอร์ `%LOCALAPPDATA%\ET-Office` + shortcut 2 จุด → ไม่มี registry/ไฟล์ตกค้าง

---

## B) Windows 11
> ทำซ้ำทุกข้อใน (A) — โฟกัสจุดที่ Win11 มักต่าง:
- [ ] ติดตั้ง install.ps1 ครบ (WebView2 มักมากับ Win11 แล้ว → ข้ามได้ถูกต้อง)
- [ ] **WorkerW embed บน Win11** — office แสดงใต้ไอคอน ไม่กระพริบ/ไม่ทับ taskbar widgets
- [ ] Snap layouts / virtual desktop สลับไปมา → wallpaper ยังอยู่ถูก ไม่หลุด parent
- [ ] M5-5 error states ครบเหมือน (A)
- [ ] ปิด + ถอน → คืน wallpaper เดิม สะอาด

---

## C) Performance & Stability (ทั้งสองเครื่อง)
- [ ] GPU usage ขณะ idle ต่ำ (เทียบเป้า M2-4: <20% บน GTX 1060) + 30 FPS cap ทำงาน
- [ ] เปิดเกม/แอป fullscreen ทับ → wallpaper auto-pause (GPU แทบเป็น 0)
- [ ] เปิดทิ้งไว้ ≥30 นาที → ไม่ memory leak, ไม่ crash, agent loop ปกติ
- [ ] ไม่มี wallpaper app อื่น (Wallpaper Engine/Lively) ชน — ถ้ามี แจ้งเตือน/pause ให้ (M2-14)

---

## Sign-off

| รายการ | Windows 10 | Windows 11 |
|--------|:----------:|:----------:|
| ติดตั้งครบ (install.ps1) | ☐ | ☐ |
| ไอคอน A-8 ขึ้นถูก | ☐ | ☐ |
| Wallpaper embed | ☐ | ☐ |
| Onboarding + task ภาษาไทย | ☐ | ☐ |
| M5-5 error/empty/loading | ☐ | ☐ |
| Performance + pause | ☐ | ☐ |
| ปิด/ถอน สะอาด | ☐ | ☐ |

- เวอร์ชันที่ทดสอบ: ____________  วันที่: ____________
- เครื่อง Win10 (GPU/VRAM): ____________  ผู้ทดสอบ: ____________
- เครื่อง Win11 (GPU/VRAM): ____________  ผู้ทดสอบ: ____________
- ผล: ☐ ผ่าน — ปล่อย v1.0 ได้   ☐ ติด blocker (ดูบันทึกด้านล่าง)

### บันทึกปัญหา / blocker
_(เขียนข้อที่ตก + repro + เครื่องที่เจอ)_
