# M20 — Orchestration Quality (Design Spec)

> สถานะ: **✅ เสร็จ (2026-06-21)** — CEO เคาะ "ตามแนะนำทั้งหมด" (P1–P4)
> เป้าหมาย: ยกคุณภาพผลงาน multi-agent บน local qwen3:8b — เลิก output generic/ซ้ำซ้อน/หลงโจทย์ + verify ตามชนิดงานจริง

## 1. ปัญหา (จาก CEO ลองสั่ง "สร้างเกม mario" → ดูไฟล์จริง)
- **หลงโจทย์ + generic:** GDD ออกมาเป็น "เกมพื้นฐาน: ตัวอย่าง" ไม่ใช่ mario
- **ซ้ำซ้อน/วางผิดที่:** มีทั้ง `scripts/PlayerMovement.cs` (Developer) + `assets/PlayerController.cs` (ซ้ำ + ผิดโฟลเดอร์)
- **ต้นตอ:** subtask รับแค่ข้อความของตัวเอง ไม่เห็นเป้าหมายเดิม + ไม่เห็นงานคนก่อน → ต่างคนต่างทำ
- **verify หลอก:** Artist เขียน `assets.md` (.md) ก็นับ "ผลิตงานแล้ว" ทั้งที่**ไม่มีไฟล์ภาพ** → Producer สรุปว่าขาดแค่เสียง ทั้งที่ภาพก็ขาด

## 2. ทางแก้ (P1–P4)

### M20-1 (P1) — Shared context ให้ subtask
แต่ละ subtask แนบ context: **เป้าหมายเดิมของ CEO** + **ไฟล์ในโปรเจกต์ตอนนี้** + **สรุปงานที่ทีมทำไปแล้ว** → กัน generic/ลืมโจทย์/ทำซ้ำ
- `_subtask_context(goal, prior)` + `_workspace_files()` ใน orchestrator
- `prior` สะสมสรุปต่อขั้น ส่งต่อให้ขั้นถัดไป

### M20-2 (P2) — Verify ตามชนิดงาน
tool-loop ติดธง **`produced_kinds`** (image/audio/code/file จากนามสกุลไฟล์จริง + generate_image สำเร็จ); orchestrator เทียบกับ **`_expected_kind(subtask)`** — งานภาพต้องได้ไฟล์ภาพ, เสียงต้องได้เสียง, code ต้องได้โค้ด ไม่งั้น mark `incomplete` → Producer สรุปตรง (ภาพขาดบอกขาด)

### M20-3 (P3) — agent สร้างสื่อไม่ได้ → เขียน spec แทน
เพิ่มกติกาใน loop prompt: เครื่องมือสร้างสื่อล้ม (key/ไม่พร้อม) หรือสร้างเสียงเองไม่ได้ → **เขียนสเปค/แผน .md แทน อย่า web_search วน** (เสริม anti-spam M19-3)

### M20-4 (P4) — Convention โฟลเดอร์
กติกา loop prompt: โค้ด→`scripts/` · asset(ภาพ/เสียง)→`assets/` · เอกสาร/ดีไซน์→`design/`

## 3. แตกงาน
| # | งาน | Tag |
|---|---|---|
| M20-1 | shared context (`_subtask_context`/`_workspace_files` + prior) | BE |
| M20-2 | `produced_kinds` (tool-loop) + `_expected_kind` + per-kind verify (orchestrator) | BE |
| M20-3 | loop prompt: media-fallback (เขียน spec แทน) | BE |
| M20-4 | loop prompt: folder convention | BE |
| M20-5 | QA Gate (`qa_m20.py`) + regression M19 | QA |

## 4. QA (qa_m20.py 15/15 + M19 11/11)
- [x] output_kind แยก png/wav/cs/md + generate_image สำเร็จ/ล้ม
- [x] expected_kind: วาด→image, เสียง→audio, code→code, design→None
- [x] context มีเป้าหมายเดิม + งานคนก่อน
- [x] orchestrator: artist(image) ได้แต่ .md → incomplete + header "งานยังไม่ครบ" + ⚠️ ระบุ artist
- [x] regression M19 ผ่าน

## 5. หมายเหตุ
- ปรับปรุงคุณภาพ "งานทีม" บน local model เล็ก — กลไกถูกแล้ว (M15/M19) M20 เติมบริบท+ความตรงของ verify
- Artist/Sound ที่ผลิตสื่อจริงไม่ได้ (key เสีย/ไม่มี audio model) → จะได้สเปค .md + รายงานตรงว่าไฟล์จริงยังขาด
