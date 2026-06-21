# M22 — Agent Liveliness, Chat & Bubbles (Design Spec — DRAFT)

> สถานะ: **📝 ร่างไว้ (2026-06-21) — ยังไม่ทำ** (CEO: "มาช่วยกันคิด สร้างเอกสารรอไว้ เดี๋ยวมาทำวันหลัง")
> เป้าหมาย: ทำให้ agent ในออฟฟิศ (wallpaper) **ดูมีชีวิต** มากขึ้น — เคลื่อนไหวเป็นธรรมชาติ, คุยเล่นน่าสนใจ, bubble เหนือหัวสื่อความรู้สึก/สถานะได้ดี

---

## 1. ของที่มีอยู่แล้ว (ฐานต่อยอด — ไม่รื้อ)
| ระบบ | ไฟล์ | ทำอะไรอยู่ |
|---|---|---|
| Speech bubble | `hud.gd` (AgentHud) | `say()` โชว์ข้อความ 7 วิ (≤90 ตัว), thinking = จุด "คิด..." ลอย, nameplate + status pill |
| Idle-roam | `agent_manager.gd` (M13-6, +M19-4) | agent ว่างเดินเล่นช่องว่าง (ไม่ยืนซ้อนแล้ว) |
| Social chat | `social_service.py` (M3-9) | จับคู่ idle ≥2 → เดินไป meeting → CrewAI คุย 2 ตา → อาจได้ proposal |
| Agent chat กับ CEO | `agent.chat` (M13-7) | คุยเล่นกับผู้ใช้ โชว์ bubble |
| FX / aura | `fx_factory`, `neon_aura`, flipbooks | ✅ done / ❌ error / ⚡ working / 💤 zzz |
| Atmosphere | `atmosphere.gd` | day/night 4 ช่วง |
| Status anim | `agent_sprite.gd` | walk / idle / sit / sleep |

→ **M22 = ขัดเงา + ขยาย ไม่ใช่สร้างใหม่จากศูนย์**

## 2. ปัญหา/ช่องว่างที่อยากแก้
- agent ตอน idle ดู "นิ่ง" เกินไป (ได้แค่เดินสุ่ม) — ขาด micro-action ให้รู้สึกมีชีวิต
- bubble จำกัด 90 ตัว, รูปแบบเดียว (ข้อความ) — ไม่มี emote/อารมณ์/reaction ต่อเหตุการณ์
- คุยเล่น (social) เกิดเฉพาะตอนจับคู่ idle → แห้ง, หัวข้อซ้ำ, ไม่มีบุคลิกต่อตัว
- agent ไม่ "รีแอคต์" ต่อเหตุการณ์งาน (เพื่อนทำเสร็จ/พัง/เสนอไอเดีย)

## 3. ข้อเสนอ (เป็นก้อน ๆ ให้เลือกทำทีหลัง)

### A. Idle micro-behaviors (ให้ไม่นิ่ง)
- สุ่ม micro-action ตอน idle: ยืดเส้น, จิบกาแฟ (เดินไป cafe), มองรอบ, พิมพ์งานที่โต๊ะ, เอนเก้าอี้
- หันหน้าสุ่ม + idle-breathing (ขยับภาพเล็กน้อย) — กันภาพแข็งทื่อ
- น้ำหนักพฤติกรรมตาม atmosphere (กลางคืน = เนือย, กลางวัน = กระตือรือร้น)

### B. Bubble & emote ที่สื่ออารมณ์
- **Emote bubble** ไอคอนเร็ว ๆ (💡❓😅🔥👍💤) ตอบเหตุการณ์ — เบากว่าข้อความเต็ม
- **Reaction ต่อ event:** task.completed → 🎉/👍, task.failed → 😵/💦, proposal → 💡, reject → 😕
- bubble หาง (tail) ชี้หัว agent ที่พูด · คิว/ไม่ทับกันเมื่อหลายตัวพูดพร้อมกัน
- typing indicator (`. . .`) ก่อนข้อความจริงโผล่ (ดูเหมือนกำลังพิมพ์)
- ปรับความยาว/เวลา bubble ตามข้อความ (ตอนนี้ fix 90 ตัว/7 วิ)

### C. โหมดคุยเล่น (Chat / banter) ที่มีชีวิต
- **บุคลิกต่อ agent:** เพิ่ม personality/tone ใน role (เช่น Producer เป็นทางการ, Artist ขี้เล่น) → social chat มีสีสัน
- **หัวข้อหลากหลาย:** หมุนหัวข้อ (งาน, เกม, ชีวิตในออฟฟิศ, ชม CEO) แทนคุยลอย ๆ
- **กลุ่มคุย:** meetup 3-4 ตัวโต้กันไปมา (ตอนนี้ 2 ตา) — bubble สลับกันเหมือนวงสนทนา
- **CEO ร่วมวง:** agent ทักผู้ใช้เป็นครั้งคราว (มีอยู่บางส่วนที่ agent.chat) — ปรับให้เป็นธรรมชาติ + คุมความถี่ไม่รบกวน
- toggle + ความถี่ปรับได้ (ต่อยอด SOCIAL LOOP setting เดิม)

### D. Ambient office life
- NPC ambiance: ไฟกระพริบ, จอเปลี่ยนภาพ, เสียง ambient ตาม zone (มี asset อยู่แล้ว A-7)
- "busy" visualization: ตอนทีมทำงานหนัก ออฟฟิศคึกคัก (เดินไปมา, จอสว่าง)

## 4. ขอบเขตเทคนิค (เบื้องต้น)
- ส่วนใหญ่ทำฝั่ง **Godot** (agent_sprite/hud/agent_manager) — event-driven จาก WS ที่มีอยู่
- โหมดคุยเล่น/บุคลิก แตะ **daemon** (`social_service`, role schema เพิ่ม `personality`) — แต่คุยเล่นใช้ local model = ฟรี ไม่กิน quota cloud
- ระวัง: บน wallpaper ห้ามกิน GPU/CPU เกิน (30fps cap เดิม) — micro-anim ต้องเบา
- bubble คุยเล่นเยอะ = ยิง local LLM บ่อย → ต้องคุมความถี่ + cache (กันเครื่องร้อน, เคารพ 1-active-local)

## 5. คำถามให้ CEO เคาะ (ตอนมาทำจริง)
1. โฟกัสก้อนไหนก่อน? (แนะนำ **B bubble/emote** เห็นผลชัดเร็วสุด + **A idle** ทำให้ไม่นิ่ง)
2. บุคลิกต่อ agent (C) — อยากกำหนดเองในไฟล์ role หรือให้ระบบสุ่ม/มี preset?
3. ความถี่คุยเล่น — เน้น "มีชีวิตตลอด" (ถี่) หรือ "ไม่รบกวน" (นาน ๆ ที)? (มี SOCIAL LOOP setting คุมได้)
4. คุยเล่นใช้ local model เท่านั้นใช่ไหม (กัน cloud quota) — ค่า default ที่ตกลง
5. มี personality/asset เพิ่ม (sprite อารมณ์, emote sheet) ที่อยากให้ทำไหม หรือใช้ของที่มี

## 6. แตกงาน (ร่าง — ปรับตอนทำ)
| # | งาน |
|---|---|
| M22-1 | Bubble/emote engine: emote icons + reaction ต่อ event + tail + คิวไม่ทับ + typing |
| M22-2 | Idle micro-behaviors (coffee/stretch/look/breathing) ตาม atmosphere |
| M22-3 | Chat mode++: personality ต่อ role + หัวข้อหมุน + กลุ่มคุย 3-4 ตัว |
| M22-4 | Ambient office life (จอ/ไฟ/เสียง ตาม zone + busy viz) |
| M22-5 | QA + จูนความถี่/ผลกระทบ GPU |

> เอกสารนี้เป็น "จุดตั้งต้น" — เดี๋ยวมาเคาะ §5 ด้วยกันก่อนลงมือ
