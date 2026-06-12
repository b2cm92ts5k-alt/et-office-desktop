# QA Gate M6 — Checklist & ผลทดสอบ (M6-10)

Gate อัตโนมัติ: `.venv\Scripts\python.exe tools\qa_m6.py`
(daemon + Ollama ต้องรันก่อน — มี `--skip-llm` ข้ามข้อ 2-3 และ `--skip-gui` ข้ามข้อ 5)

⚠️ gate จะเปิด/ปิดหน้าต่าง sidebar+terminal เองในข้อ 5 และตั้ง workspace ชั่วคราว
ใน `%TEMP%` (คืนค่า workspace เดิมให้อัตโนมัติเมื่อจบ)

## ผลรันล่าสุด — Windows 10 Pro 19045, qwen3:8b (2026-06-12) — **35/35 PASS ✅**

| ข้อ (ตาม task board) | ผล | รายละเอียด |
|---|---|---|
| 1. fire/hire + role ครบวงจร | ✅ 8/8 | /roles/save → จ้างจาก role → `agent.created` → ไล่ออก → `agent.deleted` → ลบซ้ำ 404 |
| 2. agent สร้าง-แก้ไฟล์จริงใน workspace | ✅ 7/7 | qwen tool loop เขียนไฟล์จริง เนื้อหาตรงคำสั่ง + ตอน permission เด้งไฟล์ยังไม่เกิด (gate มาก่อน action เสมอ) |
| 3. ทุก action ผ่าน permission gate | ✅ 8/8 | deny → ไฟล์ไม่เกิด / approve_task → ถามครั้งเดียว action ถัดไปเป็น `permission.auto` / ทุกคำขอ-คำตอบลง SQLite |
| 4. action นอก workspace ถูก block | ✅ 8/8 | `../`, `..\`, move/delete ออกนอก root, absolute path, ซ้อนหลายชั้น — โดน `WorkspaceError` หมด, path ถูกกติกายังใช้ได้ |
| 5. terminal window จำตำแหน่งข้าม restart | ✅ 5/5 | ย้าย+ปรับขนาดจริงผ่าน Win32 → collapse/expand ตาม sidebar → ปิด-เปิด process → rect กลับ (160,140,520,320) เป๊ะ |

## 🐛 บั๊กที่ gate จับได้ (แก้แล้วในรอบเดียวกัน)

**ขนาด terminal window ไม่คืนหลัง restart** — ตำแหน่งคืนถูกแต่ขนาดหด 520×320 → 504×281
(เท่าขอบ window มาตรฐาน 16×39px พอดี) สาเหตุ: pywebview ตั้ง Size ตอนหน้าต่างยังมี
frame แล้วค่อยถอดเป็น frameless ทำให้ ClientSize ถูกคงไว้แทน
**แก้:** `TerminalWindow.restore_geometry()` ใน `sidebar/host.py` — enforce ขนาด+ตำแหน่ง
ซ้ำใน `after_start` ซึ่งตอนนั้น resize/move ทำงานบนหน้าต่าง frameless แล้ว หน่วยตรงกัน

## ⬜ ค้างตรวจด้วยตา (ไม่บล็อค gate — broadcast ระดับ API ผ่านหมดแล้ว)

1. ⬜ Godot despawn ตัวละครเมื่อไล่ออก — gate ยืนยันแค่ `agent.deleted` broadcast
   (`agent_manager.gd` ฟัง event นี้อยู่) ตรวจภาพจริง: เปิด Godot → ไล่ agent → ตัวละครหาย
2. ⬜ permission dialog ใน sidebar แสดงรายละเอียด action + ปุ่ม 3 ปุ่มครบ
   (Approve / Deny / อนุมัติที่เหลือทั้ง task) — gate ตอบผ่าน API ตรง ไม่ได้คลิกปุ่มจริง
3. ⬜ ทดสอบบน Windows 11 (ยังไม่มีเครื่อง — รวมกับ backlog ของ QA M2)
