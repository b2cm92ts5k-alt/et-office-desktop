# ET Office — Multi-Agent Tuning Roadmap

> เอกสารแนวทางปรับ ET Office ให้ทีม agent ทำงานได้แม่นและประหยัด resource
> (มิ.ย. 2026 — CEO ทบทวนหลัง M10 launch). **เข้า board แล้ว** เป็น milestone M11 (GitHub #129–140) — เริ่มทำตามลำดับ Phase ใน §6
> อ้างอิงจาก research material ของ CEO + วิเคราะห์โค้ดจริงในโปรเจค

---

## 0. บริบทปัจจุบัน (เพื่อให้คำแนะนำต่อไปไม่ลอย)

| ระบบ | ตอนนี้ทำอะไรอยู่ | ไฟล์ |
|---|---|---|
| Orchestration | CrewAI Task router แตก message → agent ตอบทีละตัว | `daemon/services/task_router.py` |
| LLM adapter | `get_llm()` chokepoint บังคับ ollama → active tag เดียวทั้งระบบ (M7-8) | `daemon/adapters/llm_adapter.py` |
| Agent registry | per-agent มี `llm: LLMConfig` (provider + model) แต่ ollama ถูก coerce | `daemon/models/schemas.py` |
| Tool use | ToolExecutor + permission gate, workspace sandbox | `daemon/services/tool_executor.py` |
| Event/Journal | WS broadcast + replay 100 events ล่าสุด | `daemon/services/ws_manager.py` |

**กฎที่ตั้งไว้แล้ว** (อย่าฝ่า): 1 active local model ทั้งระบบ — กันรัน 2 ตัวพร้อมกันจนคอมพัง
(`[[m7-single-active-local-model]]`)

---

## 1. แนวทางจากสไลด์ CEO (สรุปสั้น — เป็นรากที่ถูกแล้ว)

### โครงสร้าง multi-agent
1. **Orchestrator/Manager** — รับ task แตก subtask แจกจ่าย ใช้ model แรงสุดที่มี
2. **Worker agents 3-5 ตัว** — role/tool แคบและชัด อย่าให้ตัวเดียวทำหลายอย่างปน
3. **Reviewer/Validator** — เช็ค output worker ก่อนส่งกลับ
4. **Flow แบบ sequential หรือ graph** ตายตัว ไม่ปล่อย orchestrator route dynamic ทั้งหมด (8B พลาดง่าย)

### Prompt/config สำหรับ Qwen3
- บังคับ JSON schema ทุก agent ที่ส่งผลต่อตัวอื่น
- system prompt สั้น เจาะจง ("ทำเฉพาะ X ห้ามทำ Y")
- ปิด `/no_think` สำหรับ worker, เปิด `/think` เฉพาะ orchestrator
- temperature 0.1-0.3 สำหรับ instruction-following, สูงไว้เฉพาะงาน creative

### แบ่งงานตาม model
- งานวางแผน/วิเคราะห์ซับซ้อน → Qwen3 14B/30B หรือ thinking mode บน 8B
- งานตรงไปตรงมา → Qwen3-8B non-thinking
- ผสม code model เฉพาะทาง สำหรับ agent เขียนโค้ด

---

## 2. ⚠️ จุดที่ขัดกับ M7-8 — ต้องเลือก path

สไลด์ #3 บอก "ผสม code model เฉพาะทาง" แต่ M7-8 บังคับ **1 active local เท่านั้น** → ขัดกันโดยตรง

**ทางออกที่ไม่ละเมิด M7-8:**
- specialist per role ทำได้ **เฉพาะผ่าน cloud API** (claude/openai/gemini) เพราะ cloud ไม่กิน VRAM
- ตัวอย่าง: Coder = Claude, Designer = GPT, Researcher = Gemini, Producer = local qwen3
- ได้ผลแบบสไลด์ #3 + ไม่ทำคอมพัง

**ทางออกที่ละเมิด M7-8 (ไม่แนะนำ):**
- ยกเลิก single-active rule, ยอมให้ local 2-3 ตัวขนานกัน → ต้องเขียน VRAM accounting ใหม่หมด + เสี่ยง OOM ทุกครั้งที่สลับ
- → **ตัดทิ้ง**

---

## 3. 6 จุดเสริมที่สไลด์ไม่ครอบ (เรียงตาม impact)

### 3.1 🔥 Constrained JSON generation (impact: สูงสุด, effort: ต่ำ)
**ปัญหา:** qwen3 หลุด schema บ่อย — สไลด์บอก "บังคับ JSON ผ่าน prompt" ไม่พอ
**วิธี:** Ollama 0.5+ รองรับ `format: <json-schema>` บังคับ output match 100%
**ไฟล์ที่จะแก้:** `daemon/adapters/llm_adapter.py` (เพิ่ม `format` param), schema ต่อ role
**ผลที่ได้:** reliability JSON-out ~30 → ~99 นาที, ตัด reviewer สำหรับ format check ได้
**เวลาประมาณ:** ครึ่งวัน

### 3.2 🔥 Retry + circuit breaker (impact: สูง, effort: ต่ำ)
**ปัญหา:** ตอน worker ตอบ JSON พังหรือ tool call ผิด ระบบไม่มี retry → agent วน loop กิน resource ไม่จบ
**วิธี:** ใน `task_router._run_task()`:
- attempt 1 → temp ปกติ
- attempt 2 → temp = 0 + เน้น schema ใน prompt
- attempt 3 → fail task, log, **ไม่ retry อีก** (circuit breaker)
**ไฟล์:** `daemon/services/task_router.py`
**ผลที่ได้:** กัน agent ตัวเดียวกินทั้งคิว, error visible ใน activity feed
**เวลาประมาณ:** ครึ่งวัน

### 3.3 🟡 Tool whitelist ต่อ role (impact: กลาง, effort: ต่ำสุด)
**ปัญหา:** ทุก agent เข้าถึง tool ชุดเดียว → designer เรียก `git push` ได้ (ไม่ควร)
**วิธี:** เพิ่ม `allowed_tools: list[str]` ใน `AgentConfig`, ToolExecutor เช็คก่อนรัน
**preset ตัวอย่าง:**
| Role | Tools |
|---|---|
| Coder/Programmer | read_file, write_file, git_commit, git_push, run_tests |
| Designer | read_file, write_file (เฉพาะใน `assets/`, `design/`) |
| Researcher | web_fetch, read_file, write_file (เฉพาะใน `research/`) |
| Producer | task_route, read_file (ไม่แตะไฟล์โค้ดตรง ๆ) |
**ไฟล์:** `daemon/services/tool_executor.py`, `daemon/models/schemas.py`
**เวลาประมาณ:** 1 ชม.

### 3.4 🔥 Context window discipline (impact: สูง, effort: กลาง)
**ปัญหา:** qwen3:8b context จริง ๆ ใช้ดีแค่ ~8-16k token แรก หลังจากนั้นคุณภาพร่วงชัด
**วิธี:**
- จำกัด history ที่ส่งเข้า model: last N messages (N=8-12)
- งานเก่า → summarize ก่อนใส่ context ใหม่ (เรียก qwen3 รอบสรุปสั้น)
- system prompt + JSON schema ต้องนับ token จริง — มี budget ชัดเจน (เช่น <=2000 token combined)
**ไฟล์:** `daemon/services/task_router.py`, role/system prompt ทุก role
**ผลที่ได้:** คุณภาพคำตอบไม่ตกตามยาวบทสนทนา, response เร็วขึ้นด้วย (context สั้น = แรง+เร็ว)
**เวลาประมาณ:** 1-2 วัน (รวมเทส)

### 3.5 🟡 Reviewer = same local + prompt ต่าง (impact: กลาง, effort: ต่ำ)
**ปัญหา:** สไลด์บอก "เพิ่ม Reviewer agent" — แต่ใน 1-local-model setup จะโหลด model เพิ่มไม่ได้
**วิธี:** ใน task_router หลัง worker ตอบเสร็จ → เรียก `active_local` รอบ 2 ด้วย prompt "ตรวจสอบ output ตาม checklist" → return เป็น `{ok: bool, issues: list}` → ถ้า `ok=false` ตีกลับ retry
**ไฟล์:** `daemon/services/task_router.py`, เพิ่ม `daemon/roles/reviewer.md` (system prompt)
**ผลที่ได้:** จับ error format/missed-instruction โดยไม่ต้องโหลด model เพิ่ม
**เวลาประมาณ:** ครึ่งวัน
**หมายเหตุ:** เปิด/ปิดได้ใน settings — บางงานเร็ว reviewer เปลือง

### 3.6 🟡 Cache layer (impact: กลาง, effort: ต่ำ)
**ปัญหา:** งานคล้ายกันถูกเรียกซ้ำ ๆ (เช่น "เขียน commit message สั้น ๆ") กิน token+เวลา
**วิธี:**
- hash `(role, system_prompt, user_input)` → cache output 5-10 นาที (LRU 100 entries)
- งาน creative (temp > 0.5) skip cache (อยากให้ random)
- cloud → ประหยัดเงินจริงเลย; local → เร็วขึ้น
**ไฟล์:** wrap ใน `daemon/adapters/llm_adapter.py`
**เวลาประมาณ:** 1-2 ชม.

---

## 4. 🌟 จุดที่ผมเน้นเป็นพิเศษ (เพิ่มเติมจากสไลด์)

### 4.1 Orchestrator = cloud ถ้ามี (เพราะ 8B พลาดเรื่องนี้บ่อยสุด)
- งาน "แตก subtask" คือ achilles heel ของ 8B
- **เริ่มต้น:** ถ้ามี cloud API key → Producer/orchestrator ใช้ cloud อัตโนมัติ
- **fallback:** ไม่มี key → ใช้ qwen3 + เปิด `/think` (thinking mode)
- ใส่เป็น hint ใน UI ตอน onboarding: "Producer แนะนำใช้ cloud — ผลลัพธ์ดีกว่า ~3 เท่า"

### 4.2 Observability ทุก hop (มี journal อยู่แล้ว เสริมแค่ field)
- ทุก WS event เพิ่ม: `model`, `provider`, `latency_ms`, `tokens_in`, `tokens_out`
- ใน UI activity feed → แสดงสถิติต่อ agent ต่อชั่วโมง (ใครช้า/พลาด/แพง)
- เป็น base สำหรับ tuning รอบถัดไป (รู้ก่อนว่า bottleneck อยู่ไหน)
**ไฟล์:** `daemon/services/task_router.py` + `sidebar/web/app.js`

### 4.3 /think vs /no_think (Qwen3-specific)
- worker ทั่วไป (เขียน, format, สรุป) → `/no_think` ใน system prompt → เร็ว 2-3x
- orchestrator + งานวางแผน → `/think` (ปล่อย thinking trace)
- เก็บใน role config: `thinking_mode: bool` field ใหม่ใน `AgentConfig`
**ไฟล์:** `daemon/models/schemas.py`, `daemon/adapters/llm_adapter.py`

### 4.4 Per-agent memory scope
- ตอนนี้ context ทุก agent share ผ่าน task_router → designer เห็น chat ของ coder
- จริง ๆ ควรแยก memory ต่อ agent (เหมือนคนจริงในออฟฟิศ)
- shared "team memory" สำหรับเรื่องที่ทั้งทีมต้องรู้ (workspace path, current sprint goal)
**effort: สูง** — เปลี่ยน task_router หลายจุด, ทำหลัง 3.1-3.6 เสร็จ

---

## 5. Specialist per role (cloud-based, opt-in)

### 5.1 Mapping เริ่มต้น (preset แนะนำ)
| Role | Provider แนะนำ | เหตุผล |
|---|---|---|
| Producer (orchestrator) | Claude (Sonnet) | วางแผน/แตกงาน หลายขั้น แม่นสุด |
| Coder/Programmer | Claude (Sonnet) | code quality สูงสุดในตลาด |
| Designer | GPT-4o | multimodal — รับภาพได้ (ในอนาคต) |
| Researcher | Gemini (Flash) | ถูก+เร็ว, web grounding ดี |
| CEO/อื่น ๆ | local qwen3 | งานทั่วไป chitchat ประหยัด |

### 5.2 UX
- **default:** local qwen3 ทุก agent (เหมือนเดิม)
- ใน HIRE dialog + gear ของ agent → ถ้ามี cloud key ใด ๆ ครบ → โชว์ banner "💡 Coder แนะนำใช้ Claude — เก่งโค้ดกว่า"
- กดยอมรับ → set `llm.provider/model` ของ agent ตัวนั้น (ไม่ยุ่ง active_local_model)
- ไม่บังคับ — CEO สั่งเองเสมอ

### 5.3 Cost guard (สำคัญถ้าเปิด cloud)
- เพิ่ม budget ต่อวัน/ชั่วโมง ใน settings (เช่น $5/วัน)
- เกิน → fallback กลับ local + แจ้งใน activity feed
- ป้องกัน 8B หลุดทำ loop เรียก Claude ไม่จบ
**ไฟล์ใหม่:** `daemon/services/cost_guard.py`

---

## 6. ลำดับแนะนำ (ถ้าเริ่มทำ)

### Phase 1 — Reliability quick wins (1-2 สัปดาห์)
1. **3.1** Constrained JSON (ครึ่งวัน) — base ของทุกอย่าง
2. **3.2** Retry + circuit breaker (ครึ่งวัน)
3. **3.3** Tool whitelist (1 ชม.)
4. **3.6** Cache layer (1-2 ชม.)
5. **4.2** Observability fields (ครึ่งวัน)

### Phase 2 — Quality (1 สัปดาห์)
6. **3.4** Context window discipline (1-2 วัน)
7. **3.5** Reviewer-same-model (ครึ่งวัน)
8. **4.3** /think vs /no_think per role (2-3 ชม.)

### Phase 3 — Cloud + specialist (เลือกทำเมื่อพร้อม)
9. **5.1-5.2** Specialist per role + UI banner (1-2 วัน)
10. **5.3** Cost guard (1 วัน)

### Phase 4 — Advanced (ใหญ่ ทำทีหลัง)
11. **4.4** Per-agent memory scope (1 สัปดาห์)

---

## 7. ของที่ไม่แตะ (สรุปไว้ป้องกัน scope creep)

- ❌ **ไม่** ยกเลิก single-active-local rule (M7-8)
- ❌ **ไม่** ทำ orchestrator dynamic routing บน 8B (สไลด์เตือนแล้ว — 8B พลาด)
- ❌ **ไม่** เปลี่ยน CrewAI เป็น framework อื่น (LangGraph/AutoGen) จนกว่าจะมีเหตุชัด
- ❌ **ไม่** เพิ่ม local model ตัวที่ 2 ใน VRAM พร้อมกัน

---

## 8. Related memory / docs
- `[[m7-single-active-local-model]]` — กฎ 1 active local (ห้ามฝ่า)
- `[[et-office-ceo-feature-expansion]]` — model strategy ที่ตกลงไว้
- `daemon/roles/*.md` — system prompt ของแต่ละ role (ที่จะถูกแก้ใน Phase 1.1)
