# M15 — Real Teamwork & Skills (Design Spec)

> สถานะ: **✅ เสร็จ (2026-06-20)** — M15-1/2/3/4/5/7 + QA 30/30 (M15-6 approve-plan CEO เคาะไม่ทำ)
> เป้าหมาย: ทำให้ ET Office "ทำงานได้จริง + ทำงานร่วมกันจริง" มีประโยชน์ต่อผู้ใช้
> CEO เทสแล้ว: การมอบหมายงานทีมใช้ได้ดี ✅
>
> **ไอเดียเก็บไว้เวอร์ชันอนาคต (CEO 2026-06-20):**
> 1. approve-plan แบบ setting เปิด/ปิดได้ (default ปิด=auto) — กดอนุมัติ plan ก่อนทีมลงมือ
> 2. ตั้ง tool ต่อ role ผ่าน API/ปุ่ม — apply ROLE_TOOL_PRESETS อัตโนมัติ แทนติ๊กมือทีละตัว

---

## 1. ปัญหา (จากที่ CEO ลองใช้จริง)

ET Office ตอนนี้ = **single-agent ต่อ 1 คำสั่ง** — CEO สั่ง → `_match_agent` เลือก agent 1 ตัวตาม keyword → tool-loop ทำคนเดียว → จบ

ช่องว่าง:
- **ไม่มีการแตกงาน (decompose)** → งานซับซ้อนได้แค่บางส่วน ("ทำได้แต่น้อยไป")
- **agent ไม่มอบหมายงานให้กันจริง** ("collab" = แค่เดินไปคุยเล่น social ไม่ใช่ทำงาน)
- **agent local (qwen3) ไม่มีสูตรทำงาน** → เดาเองทีละขั้น หลุดบ่อยกับงานหลายขั้น
- **ค้นข้อมูลเองไม่ได้** (`fetch_url` ดึงได้แค่ URL ที่รู้แล้ว ไม่มี web search)

พื้นฐานที่ดีอยู่แล้ว (ไม่ต้องรื้อ): tool-loop เสถียร (M11), ToolExecutor, per-agent memory, roles `.md`, permission gate, cost_guard, specialist preset.

---

## 2. ภาพรวมสถาปัตยกรรม M15

> **CEO เคาะ (2026-06-20): ET Office ใช้หลักการ Sub-Agent อย่างเดียว** — ไม่มี mode toggle, ไม่มี
> single-agent mode แยก, ไม่มี Multi-Agent peer mode. **ทุกคำสั่งเข้า orchestrator เสมอ** (งานง่าย
> = orchestrator ออก plan แค่ 1 subtask ก็พอ ไม่เปลือง)

3 ชิ้นต่อยอดของเดิม:

```
                        ┌─────────────── SKILLS (ชิ้น A) ───────────────┐
                        │  skill_service: match task → inject สูตรเข้า   │
                        │  system prompt ของ tool-loop (sub-agent ได้)  │
                        └───────────────────────────────────────────────┘
CEO สั่ง                                  │ ใช้ทุก subtask
   ▼                                      ▼
[Producer = orchestrator]  (ชิ้น B — เส้นทางเดียวเสมอ)
   │ 1) decompose → plan JSON [{role, subtask, depends_on}]  (งานง่าย = 1 subtask)
   │ 2) เสนอ plan ให้ CEO อนุมัติ (อนุมัติทั้งก้อน)
   ├─→ et-researcher : subtask (+web_search ชิ้น C +skill)
   ├─→ et-programmer : subtask (+skill build-feature)
   ├─→ et-designer   : subtask
   │ 3) รวมผล (synthesize) → ตอบ CEO
 (Godot: agent สว่างทีละตัวตามที่ถูกมอบงาน)
```

- **ชิ้น A — Skills system:** สูตรทำงานทีละขั้น (markdown) inject เข้า prompt → boost ทุก sub-agent
- **ชิ้น B — Orchestrator (Sub-Agent, เส้นทางเดียว):** Producer แตกงาน→มอบหมาย→รวมผล (reuse tool-loop เดิมต่อ subtask) + Godot โชว์ delegation
- **ชิ้น C — Tools:** `web_search` (+ optional run/test)

---

## 3. ดีไซน์รายชิ้น

### A. Skills System

**Skill = ไฟล์ markdown** เก็บที่ `daemon/data/skills/<name>.md`:
```markdown
---
name: research-and-report
description: ใช้เมื่อต้องค้นข้อมูลแล้วสรุปเป็นรายงาน/เอกสาร
tools: [web_search, fetch_url, write_file]
when: ["ค้นหา","วิจัย","สรุป","รายงาน","research"]
---
ขั้นตอน:
1. web_search หัวข้อ → เลือก 3-5 แหล่งน่าเชื่อถือ
2. fetch_url แต่ละแหล่ง → จดประเด็นสำคัญ
3. เรียบเรียง → write_file รายงาน .md (มีหัวข้อ/อ้างอิง)
4. สรุปสั้นให้ CEO
```

**Loader/matcher (`skill_service.py`):**
- `match_skills(message, role) -> list[skill]` — match จาก `when` keywords + `description` (เริ่มแบบ keyword overlap = ถูก/เร็ว/เสถียร; อัปเกรดเป็น embedding ทีหลังได้)
- inject body ของ skill ที่ match ดีสุด 1 (สูงสุด 2) เข้า system prompt ใน `_run_tool_loop` — เคารพ context budget (M11-6); skill ยาวเกิน budget → clip
- skill อ้าง **tool จริงของ ET Office** เท่านั้น

**Skill ชุดแรก (เขียนเองเฉพาะ ET Office, ภาษาไทย):**
1. `research-and-report` — ค้น→สรุป→เขียนรายงาน
2. `build-feature` — วางแผน→เขียนไฟล์→ทดสอบ→commit
3. `write-plan` — แตกงานเป็นขั้น เขียน plan doc
4. `organize-files` — จัดระเบียบไฟล์/โฟลเดอร์ใน workspace
5. `small-game-team` — workflow ทำเกมเล็กเป็นทีม (CEO เคาะเพิ่ม) — GDD → asset/art → โค้ด gameplay → ทดสอบ; map บทบาท game-designer/artist/programmer ให้ orchestrator ใช้แตกงานเกม

**UI:** Settings → Skills (list / เปิด-ปิด / ดู / เพิ่มเอง — รูปแบบเดียวกับ roles M6-2) + AI ช่วยร่าง skill (เหมือน M6-3)

### B. Orchestrator (Sub-Agent mode)

**flow ใหม่ (`orchestrator_service.py`):**
1. **decompose** — orchestrator (Producer) ยิง LLM constrained-JSON (M11-1) → `plan = [{role, subtask, depends_on}]`
2. **(option) approve plan** — เสนอ plan ให้ CEO ดู/อนุมัติก่อนลงมือ (ผ่าน proposal/permission)
3. **dispatch** — แต่ละ subtask → `task_router.run_sync()` บน agent ที่ role ตรง (reuse tool-loop เดิม 100%) — ทำตามลำดับ depends_on (independent = ทำต่อเนื่องได้)
4. **synthesize** — รวมผลทุก subtask → orchestrator เรียบเรียงคำตอบสุดท้าย → ตอบ CEO
5. broadcast status ทุกขั้น → Godot โชว์ agent ทำงานทีละตัว

**reuse สูงสุด:** subtask = tool-loop เดิม + permission gate เดิม + cost_guard เดิม. โค้ดใหม่ = แค่ loop decompose/dispatch/synthesize

### C. Tools เพิ่ม
- **`web_search(query)`** (สำคัญสุด) — คืน title+snippet+url 5-8 รายการ → agent ค่อย `fetch_url` ตัวที่เลือก
- *(optional)* `run_python` / `run_tests` — รัน+เห็นผลจริง (powershell มีแล้ว ใช้แทนได้ระดับหนึ่ง)
- ทุก tool ใหม่ผ่าน permission gate + tool whitelist (M11-3) เหมือนเดิม

### D. Godot delegation viz (ไม่มี mode toggle แล้ว)
- **ตัด mode toggle + single mode + Multi-Agent peer mode ทิ้งทั้งหมด** (CEO เคาะ) — เหลือเส้นทางเดียว = orchestrator เสมอ
- Godot: broadcast status ทุกขั้นของ orchestrate → agent สว่าง/เดินไปทำงานทีละตัวตาม subtask

---

## 4. จุดที่ต้องเคาะ (พร้อมคำแนะนำของผม)

| # | ประเด็น | ตัวเลือก | 💡 ผมแนะนำ |
|---|---------|----------|-----------|
| D1 | **Model ของ orchestrator** (decompose = reasoning หนักสุด) | local qwen3 เท่านั้น / แนะนำ cloud ถ้ามี key | **cloud ถ้ามี key (Producer→Claude Sonnet ตาม preset เดิม) fallback local** — decompose แม่นขึ้นเยอะ |
| D2 | **Permission ตอน orchestrate** (หลาย agent ลงมือ = prompt เยอะ) | per-action ทุกครั้ง / อนุมัติ plan ทั้งก้อนทีเดียว | **อนุมัติ plan ก่อนเริ่ม + ยัง gate เฉพาะ tool เสี่ยง (delete/powershell/push)** |
| D3 | **web_search ใช้อะไร** | keyless (DuckDuckGo) / API key (Brave/Serp) | **keyless default + เสียบ API key ได้ถ้าอยากแม่นขึ้น** (ไม่บังคับมี key) |
| D4 | **Multi-Agent peer mode + toggle** | ~~ทำ/เลื่อน~~ | ✅ **CEO เคาะ: ตัดทิ้งทั้งหมด — Sub-Agent เส้นทางเดียว** |
| D5 | **Skill matching** | keyword / LLM เลือก / embedding | **keyword ก่อน** (ถูก/เร็ว/เสถียร) อัปเกรดทีหลัง |
| D6 | **ลำดับทำ** | Skills ก่อน / Orchestrator ก่อน | ✅ **Skills ก่อน** (CEO เคาะ) |

**สถานะการเคาะ (2026-06-20):** D1 ✅ cloud-fallback-local · D2 ✅ approve-plan · D3 ✅ keyless+optional key · D4 ✅ ตัด multi-agent/toggle · D5 ✅ keyword · D6 ✅ Skills ก่อน · "ที่เหลือทำตามที่แนะนำ"

---

## 5. Task breakdown (ร่าง — ปรับหลังเคาะ)

| ID | งาน | Tag |
|----|-----|-----|
| M15-1 | Skill infra — `skill_service.py` (match+inject) + integrate เข้า `_run_tool_loop` + context budget | BE |
| M15-2 | เขียน skill ชุดแรก 5 ตัว (research-report / build-feature / write-plan / organize-files / small-game-team) | BE/DOC |
| M15-3 | Skills UI — Settings panel (list/เปิด-ปิด/ดู/เพิ่ม + AI ช่วยร่าง) | UI |
| M15-4 | `web_search` tool (keyless + optional key) + permission/whitelist | BE |
| M15-5 | `orchestrator_service.py` — decompose→dispatch→synthesize (reuse run_sync) — **เส้นทางเดียวเสมอ** | BE |
| M15-6 | Orchestrator: approve-plan + cost/permission flow (decompose แนะนำ cloud, fallback local) | BE |
| M15-7 | Godot — โชว์ agent ทำงานทีละตัวตาม subtask (delegation viz) | GODOT |
| M15-8 | QA Gate M15 (skill inject, orchestrate e2e, web_search) | QA |

*(ตัดออกตาม CEO: mode toggle, single-mode แยก, Multi-Agent peer mode)*

---

## 6. Risks
| Risk | Mitigation |
|------|------------|
| qwen3 local decompose ไม่แม่น → plan มั่ว | D1 แนะนำ cloud + constrained JSON + fallback ทำคนเดียวถ้า decompose ล้มเหลว |
| orchestrate กิน token/เงินบาน | cost_guard เดิม + approve-plan + จำกัดจำนวน subtask/ความลึก |
| skill ยาวกิน context | clip ตาม budget (M11-6) + inject สูงสุด 1-2 skill |
| permission prompt ถี่จนน่ารำคาญ | D2 approve-plan ทั้งก้อน |
| web_search โดน block/เปลี่ยน HTML | keyless ทำ fallback + เปิดทาง API key |
