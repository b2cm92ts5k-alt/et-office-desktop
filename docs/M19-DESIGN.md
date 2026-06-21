# M19 — Orchestration Reliability & Polish (Design Spec)

> สถานะ: **🚧 กำลังทำ (2026-06-21)** — CEO เคาะ "ตามแนะนำ" ทั้ง 3 กลุ่ม
> เป้าหมาย: แก้ "งานหลอกว่าเสร็จ" หลังกด REJECT + tool รั่ว (web_search วน) + agent ยืนซ้อน/Producer ผิดที่

## 1. ปัญหา (จาก CEO ลองจริง)
1. **กด REJECT แล้วงานไม่หยุด + หลอกว่าเสร็จ** — reject = สัญญาณอ่อน ("สรุปเท่าที่ทำได้") → agent ปั้น final ส่งทั้งที่ไฟล์ไม่ได้สร้าง → orchestrator ไม่มีแนวคิด "subtask ล้ม" → Tester รันต่อบนไฟล์ที่ไม่มี → Producer สรุป "เสร็จ"
2. **tool รั่ว** — Artist (qwen3:8b) วน `web_search` ไม่จบ (แต่ละครั้ง "สำเร็จ" → ไม่ติด circuit breaker → จน MAX_STEPS) เพราะ generate_image ใช้ key เสีย + ไม่มี guard จับ tool ซ้ำไม่คืบ
3. **agent ยืนซ้อน / Producer ผิดที่** — idle roam ใช้ `ROAM_SPOTS.pick_random()` ไม่จอง; Producer ไม่มีโต๊ะประจำ

## 2. ทางแก้ (CEO เคาะ)
**Logic:** reject = subtask ล้มจริง (ไม่ปั้น final) + รายงานตามจริง + skip ขั้นที่พึ่งกัน · verify ก่อนบอกเสร็จ · ตัด tool รั่ว
**Godot:** จอง roam (ไม่ซ้อน) + Producer โต๊ะ lead ประจำ

## 3. แตกงาน

### M19-1 — REJECT = subtask ล้มจริง (ไม่หลอกเสร็จ)
- เพิ่ม `_Rejected(Exception)` — permission ถูก deny → **raise** (เลิก observation "สรุปเท่าที่ทำได้")
- `_run_tool_loop_retry`: `_Rejected` **ไม่ retry** (re-raise ทันที — user ปฏิเสธไม่ใช่ความผิดพลาดที่ลองใหม่ได้)
- orchestrator: subtask ที่ raise → มาร์ก **failed**; ถ้าเป็น **reject → หยุด dispatch ขั้นที่เหลือ (skip)** เพราะมักพึ่งกันตามลำดับ; error อื่น → ทำขั้นที่เหลือต่อได้
- single task (ไม่ orchestrate): reject → task.failed ตรง ๆ (honest)

### M19-2 — Honest synthesize + verify (เลิกหลอกว่าเสร็จ)
- `results` เก็บสถานะต่อ subtask: `done | failed | skipped`
- `_synthesize`: **header คำนวณจากโค้ด** (ไม่พึ่ง LLM) — มีขั้นไม่สำเร็จ → ขึ้น "⚠️ งานยังไม่ครบ (N/M ขั้นสำเร็จ)" + ลิสต์สถานะแต่ละขั้น; prompt สั่งห้ามบอก "เสร็จสมบูรณ์" ถ้ามี ❌/⏭️
- verify เบื้องต้น: tool-loop ติดธง `produced_output` (มี write/mkdir/generate_image/git_commit สำเร็จ ≥1) → ส่งกลับให้ orchestrator ใช้ประกอบสถานะ

### M19-3 — Anti tool-spam guard (กัน web_search วน)
- tool-loop track signature `(tool, args)` ซ้ำ: ครบ 3 ครั้ง → แทรก nudge แรง ("หยุดเรียก X ซ้ำ เปลี่ยนวิธีหรือสรุป final"); ครบ 5 → `_AttemptFailed` (ตัดวง → retry/จบ)
- generate_image ล้ม (key เสีย) → คืน error ชัด + guard นี้กันวน
- (config) แนะนำ CEO ตั้ง image_model ของ Artist เป็น key ที่ใช้ได้

### M19-4 — Godot positioning
- **Producer โต๊ะประจำ:** `PRODUCER_DESK` (เช่น (5,2) — lead หน้าแถว ข้าง CEO) assign ให้ agent role producer, ออกจาก pool สุ่ม
- **roam ไม่ซ้อน:** `_roam_tick` เลือก ROAM_SPOT ที่ว่าง (ไม่มี agent ยืน/มุ่งหน้าไป) ผ่าน `_dest_of` map; เต็ม → อยู่กับที่
- (deeper: agent เป็น obstacle ตอนเดินผ่านกัน = future — เสี่ยง + เทส Godot สดไม่ได้)

### M19-5 — QA Gate
- offline: reject→fail (ไม่ retry, ไม่หลอกเสร็จ), synthesize honest header, anti-spam ตัดวง, produced_output flag

## 4. QA / Acceptance
- [ ] reject action → subtask นั้น failed (ไม่ปั้น final) + ไม่ retry
- [ ] reject ใน orchestrate → ขั้นที่เหลือ skip + Producer สรุป "⚠️ ยังไม่ครบ" (ไม่หลอกเสร็จ)
- [ ] เรียก tool เดิม 5 รอบ → ตัดวง (ไม่วนจน MAX_STEPS)
- [ ] subtask ที่ไม่สร้างไฟล์เลย → produced_output=false สะท้อนในสถานะ
- [ ] Godot: roam ไม่ยืนซ้อน + Producer อยู่โต๊ะ lead (syntax ok; เทสจริงโดย CEO)
- [ ] ของเดิมไม่พัง (งานปกติที่ approve หมด ยังเสร็จ + สรุปเหมือนเดิม)
