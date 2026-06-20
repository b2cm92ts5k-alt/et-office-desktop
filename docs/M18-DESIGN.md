# M18 — Role Tool Presets (Design Spec)

> สถานะ: **🚧 กำลังทำ (2026-06-21)** — CEO สั่งทำเลย (ไอเดียจดไว้ตั้งแต่ M15)
> เป้าหมาย: สร้าง agent ใหม่แล้ว **tool ถูกติ๊กให้ตรง role อัตโนมัติ** — ไม่ต้องนั่งติ๊กทีละตัว

## 1. ปัญหา
`ROLE_TOOL_PRESETS` มีอยู่แล้วใน [`tool_executor.py`](../daemon/services/tool_executor.py) แต่ **ไม่ได้ถูกใช้ที่ไหนเลย** (มีแต่ใน QA) — ไม่มี matcher / endpoint / ปุ่ม UI. เวลาจ้าง agent ใหม่ `allowed_tools` ว่าง (= อนุญาตทุก tool) หรือ CEO ต้องเข้า Gear ติ๊กเองทีละตัว

## 2. หลักการ
3 ชิ้นเติมของเดิม (ไม่รื้อ):
1. **ขยาย presets + matcher** — role เป็น free-text ไทย (เช่น "Sound Designer") → จับเข้า preset ที่ถูกด้วย keyword (pattern เดียวกับ `specialist_for`)
2. **endpoint** `GET /tools/presets` — คืน preset ทั้งหมด + ตัวที่ match กับ role
3. **UI** — ปุ่ม "🎯 ใช้ tool ตาม role" ใน Gear (ติ๊กให้) + HIRE auto-apply ตอนสร้าง

## 3. Preset matrix (เริ่มต้น — CEO ปรับได้ ทุก tool ยังติ๊กเอง override ได้)
| preset | tools | จับจาก keyword |
|---|---|---|
| producer | read_file, list_dir, gh_* | producer/manager/เลขา/วางแผน/orchestrat/pm |
| coder | read/write/list/mkdir/move, git_* | coder/program/developer/dev/engineer/โปรแกรม/วิศวกร |
| artist | generate_image, read/write/list/mkdir | artist/วาด/ภาพ/image/art/กราฟิก/illustrat/concept |
| sound | read/write/list/mkdir | sound/เสียง/audio/music/ดนตรี/sfx/composer |
| tester | read_file, list_dir, web_search, git_status, git_diff | test/qa/ทดสอบ/คุณภาพ/bug |
| writer | read/write/list, web_search, fetch_url | writ/narrative/เนื้อเรื่อง/story/script/นักเขียน/lore |
| researcher | read/write/list, web_search, fetch_url | research/วิจัย/ค้นคว้า/หาข้อมูล/วิเคราะห์/analyst |
| designer | read/write/list/mkdir | design/ออกแบบ/ui/ux/ดีไซน์/level |

> ลำดับ match สำคัญ: sound/tester/writer มาก่อน "designer" → "Sound Designer" จับ sound (ไม่ใช่ designer), "Game Designer" จับ designer

## 4. API
`GET /tools/presets?role=&keywords=` → `{presets: {...}, match: {preset, tools} | null}`
- `match` = preset ที่ตรง role (UI เอา tools ไปติ๊ก); `presets` = ทั้งหมด (เลือกเองได้)

## 5. UI
- **Gear:** ปุ่ม "🎯 ใช้ tool ตาม role (<preset>)" เหนือ checklist → ติ๊ก tool ของ preset ที่ match (ไม่ลบที่ติ๊กเองไว้ — union). ไม่ match → ปุ่มเทา/ซ่อน
- **HIRE:** ตอนกดจ้าง ถ้าไม่ได้ตั้ง allowed_tools เอง → auto-apply preset ที่ match role (agent ใหม่มาพร้อม tool ที่ใช่) + แจ้ง feed สั้น ๆ

## 6. แตกงาน
| # | งาน |
|---|---|
| M18-1 | ขยาย ROLE_TOOL_PRESETS (sound/tester/writer) + `preset_for_role()` matcher + `GET /tools/presets` |
| M18-2 | UI Gear — ปุ่ม "🎯 ใช้ tool ตาม role" ติ๊ก preset ที่ match |
| M18-3 | UI HIRE — auto-apply preset ตอนสร้าง agent ใหม่ |
| M18-4 | QA Gate (matcher ถูก role, endpoint, ลำดับ sound/game designer) |

## 7. QA / Acceptance
- [ ] "Sound Designer" → preset sound · "Game Designer" → designer · "Developer" → coder · "ET Artist" → artist
- [ ] `GET /tools/presets?role=...` คืน match ถูก
- [ ] Gear: กดปุ่ม → tool ของ preset ถูกติ๊ก (union กับที่ติ๊กเอง)
- [ ] HIRE: จ้าง agent role ใหม่ → allowed_tools มาจาก preset อัตโนมัติ
- [ ] role แปลก (ไม่ match) → ไม่ crash, ไม่ติ๊กอะไร (= ทุก tool ตาม default เดิม)
