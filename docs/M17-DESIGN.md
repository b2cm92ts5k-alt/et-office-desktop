# M17 — Image Generation (ET Artist) Design Spec

> สถานะ: **📝 ออกแบบ (2026-06-21)** — รอ CEO เคาะเริ่มทำ
> เป้าหมาย: ให้ ET Office มี agent ที่ **สร้างภาพได้จริง** (ET Artist) ด้วยโมเดลสร้างภาพ — เริ่มจากของฟรีที่มีอยู่แล้ว (Nano Banana ผ่าน Gemini key) และ **เลือกอัปเป็นโมเดลเสียเงินได้** เมื่ออยากได้งานโหดขึ้น
>
> **ไอเดียหลักจาก CEO (2026-06-21):** หลังเปิด tool สร้างภาพให้ agent แล้ว ผู้ใช้ต้อง **เลือกโมเดลสร้างภาพแยกได้เอง** (คนละตัวกับ "สมอง" chat ของ agent) — เผื่ออยากสลับไปโมเดลเสียเงินคุณภาพสูง
>
> **CEO เคาะแล้ว (2026-06-21) — ตามที่แนะนำทั้ง 6 ข้อ (§12):** v1 = text→image · default = Nano Banana (ฟรี) · แสดงผล sidebar thumbnail + Godot hologram · permission ทุกครั้ง · n=1 (สูงสุด 4) · provider เริ่ม Gemini(ฟรี)+OpenAI(paid) → branch `m17-image-generation`, issues #180–#188
>
> ต่อยอดโดยตรงจาก [`M16-DESIGN.md`](M16-DESIGN.md): ใช้ provider registry + per-account model cache + การ classify `kind:image` ที่ทำไว้แล้ว

---

## 1. ปัญหา / ทำไมต้องมี

ET Office **ยังไม่มี agent ที่สร้างภาพได้** — ET Artist ตอนนี้ทำได้แค่คุย/เขียนไฟล์ เพราะ:

- **agent ทุกตัวใช้ "สมอง" เป็น chat model** (รับข้อความ → คิด → เรียก tool → ตอบข้อความ) ผ่าน CrewAI tool-loop
- **model สร้างภาพเป็นคนละชนิด** (prompt → รูป ไม่ใช่บทสนทนา) → เสียบเป็นสมอง agent ไม่ได้ (M16 จึง classify เป็น `kind:image` แล้วปิดเลือกในช่องสมอง — ถูกต้อง)

**ทางออกที่ถูก:** การสร้างภาพต้องเป็น **เครื่องมือ (tool)** ที่ agent (สมอง chat) เรียกใช้ — ไม่ใช่สลับสมอง. ET Artist = chat brain (วางแผน/แต่ง prompt) + tool `generate_image` (เรนเดอร์จริง)

ของดีที่มีอยู่แล้ว (ไม่ต้องรื้อ): `TOOLS_SPEC`/`execute()` ([`tool_executor.py`](../daemon/services/tool_executor.py)) คืน string observation, `allowed_tools` whitelist (M11-3), permission gate (M6-8), workspace sandbox, **M16 cache+classify image model ต่อ key แล้ว**, `_resolve_cloud_key` (M14/M16)

---

## 2. หลักการออกแบบ

```
ET Artist agent
 ├─ สมอง (llm)        = chat model (local qwen / GPT-4.1 / Gemini) — แต่ง prompt, ตัดสินใจ
 └─ tool generate_image
       └─ image_model (เลือกแยก!) = Nano Banana (ฟรี) / Imagen / gpt-image-1 (เสียเงิน) ...
              └─ image_adapter → ยิง API ของ provider → ได้ PNG → เซฟ workspace → โชว์
```

3 เสาหลัก:
1. **`generate_image` tool** — เพิ่มใน `TOOLS_SPEC`/`execute()`, เซฟ PNG ลง workspace, คืน path + ยิง WS event โชว์ผล
2. **Image Adapter** — ตัวแปลงต่อ provider (Gemini/OpenAI/OpenRouter) เพราะ API สร้างภาพ **ต่างจาก chat** (คนละ endpoint/รูปแบบ) — pattern เดียวกับ M16 registry, reuse `_resolve_cloud_key`
3. **เลือก image model แยก (ไอเดีย CEO)** — `AgentConfig.image_model` (คนละช่องกับสมอง `llm`); picker ใน Gear ป้อนจาก image-kind models ที่ M16 cache ไว้ (ฟรี*/เสียเงิน ตามจริง)

---

## 3. เสา A — `generate_image` tool

เพิ่มใน `TOOLS_SPEC`:
```python
"generate_image": {"args": ["prompt", "filename"], "desc":
    "สร้างรูปจากคำอธิบาย (prompt ภาษาอังกฤษได้ผลดีสุด) → เซฟเป็น PNG ใน workspace/artwork/"},
```
ใน `execute()` (เคส `generate_image`):
1. อ่าน `image_model` ของ agent ที่เรียก (provider/model/account_id) — default = ฟรี (ดู §5)
2. `key = _resolve_cloud_key(provider, account_id)` → ไม่มี key ที่สร้างภาพได้ → คืนข้อความแนะนำ "เพิ่ม Gemini key (ฟรี) ที่ Settings"
3. `image_adapter.generate(provider, model, key, prompt, opts)` → คืน `bytes` (PNG)
4. เซฟ `workspace/artwork/<ts>_<slug>.png` (ผ่าน `_resolve` sandbox เดิม — กันหลุด workspace)
5. ยิง WS event `image.generated {agent_id, path, prompt, model}` (โชว์ใน Godot/sidebar — §7)
6. คืน observation: `"สร้างรูปแล้ว: artwork/xxx.png (model: …)"` ให้สมอง agent อ่านต่อ

> tool คืน **string** เสมอ (ตาม contract เดิม) — ไม่คืน binary; รูปอยู่ในไฟล์ + event

**args เสริม (เสนอ v1):** `n` (จำนวนรูป, default 1, สูงสุด 4), `aspect` (1:1 / 16:9 / 9:16). ตัวเลือกขั้นสูง (seed, negative prompt) ไว้ v2

---

## 4. เสา B — Image Adapter (routing ต่อ provider)

ไฟล์ใหม่ `daemon/adapters/image_adapter.py` — API สร้างภาพต่างกันมาก จึงต้องมี adapter แยก (ไม่ผ่าน CrewAI LLM):

| provider | model (ตัวอย่าง) | endpoint / รูปแบบ |
|---|---|---|
| **gemini** (Nano Banana) | `gemini-2.5-flash-image`, `gemini-3-pro-image`, `gemini-3.1-flash-image` | `:generateContent` → `candidates[].content.parts[].inline_data.data` (b64 PNG) |
| **gemini** (Imagen) | `imagen-4.0-generate-001` / ultra / fast | `:predict` → `predictions[].bytesBase64Encoded` |
| **openai** | `gpt-image-1`, `dall-e-3` | `POST /v1/images/generations` (`response_format=b64_json`) |
| **openrouter** | `black-forest-labs/flux-*` ฯลฯ | chat/completions modality image (ปรับตอนทำ) |

โครง (mirror M16 — เพิ่ม `image` capability ใน PROVIDERS หรือแยก `IMAGE_PROVIDERS`):
```python
def generate(provider, model, key, prompt, *, n=1, aspect="1:1") -> list[bytes]:
    fn = _IMAGE_BACKENDS.get(provider)        # gemini_nano / gemini_imagen / openai / openrouter
    if not fn: raise ImageError(f"{provider} สร้างภาพไม่ได้")
    return fn(model, key, prompt, n=n, aspect=aspect)
```
- เลือก backend ของ gemini ตาม model id: มี `imagen` → predict; อื่น (`*-image`) → generateContent
- timeout + จำกัดขนาด, แปลง b64 → bytes, validate เป็น PNG/JPEG

> verify ตอนทำ: shape ของ Nano Banana `inline_data` + Imagen `:predict` + gpt-image-1 ปัจจุบัน (ปรับที่ adapter จุดเดียว)

---

## 5. เลือก image model แยก (หัวใจตามไอเดีย CEO)

### 5.1 data model
`AgentConfig` เพิ่มฟิลด์ (reuse รูป `LLMConfig`: provider/model/account_id):
```python
image_model: LLMConfig | None = None   # โมเดลของ tool generate_image — None = ใช้ default ฟรี
```
- แยกขาดจาก `llm` (สมอง chat) → สมองเป็น local qwen ก็ได้ แต่วาดด้วย Nano Banana/gpt-image
- เก็บแค่ provider/model/account_id (ไม่เก็บ secret — เหมือน M14/M16)

### 5.2 default = ฟรีอัตโนมัติ
ถ้า `image_model` ว่าง → resolve default:
1. มี Gemini key → `gemini` / `gemini-2.5-flash-image` (Nano Banana, ฟรี*)
2. ไม่มี → ตัวแรกของ image-kind จาก account ใด ๆ
3. ไม่มีเลย → tool คืนข้อความแนะนำเพิ่ม key (ไม่ error ดิบ)

### 5.3 endpoint ป้อน picker (reuse M16)
`GET /models/available?kind=image` (ขยาย M16-4) — คืน image-kind models จาก account cache + ป้าย `_price_tag` (ฟรี*/💰 ราคา) เหมือนช่องสมอง → ทุกอย่าง consistent กับ M16

### 5.4 UI (Gear ของ agent)
- โชว์ช่อง **"🎨 Model สร้างภาพ"** *เฉพาะเมื่อ* tick tool `generate_image` ใน checklist (M11-3) → ไม่รก agent ที่ไม่วาดรูป
- dropdown รูปแบบเดียวกับ M16 (optgroup ☁ Cloud, ป้าย 🟢 ฟรี* / 💰 $.../img) + key picker ถ้า cloud
- default เลือก Nano Banana (ฟรี) ให้อัตโนมัติ — CEO สลับเป็น gpt-image-1/Imagen เองได้

---

## 6. Permission + Cost (กันเงินรั่ว)

- `generate_image` **ผ่าน permission gate ทุกครั้ง** (สร้างไฟล์ + อาจเสียเงิน) — dialog โชว์: prompt ย่อ + model + ป้าย **ฟรี/💰 ราคาประมาณ/รูป**
- โมเดลเสียเงิน → เน้นเตือนใน dialog (เช่น "gpt-image-1 ~$0.04/รูป × n")
- **cost_guard** เพิ่มหน่วย **per-image** (ของเดิม per-token): ราคาประมาณ/รูป — gpt-image-1 ~$0.01–0.17, dall-e-3 ~$0.04–0.12, Imagen ~$0.04, Nano Banana = ฟรี (quota). นับรวมเพดานรายวัน/ชม. เดียวกับ M11-10
- `summarize()` เพิ่มเคส generate_image → "สร้างรูป: <prompt ย่อ> (model)"

---

## 7. แสดงผล (Godot + sidebar)

- WS event `image.generated {agent_id, path, prompt, model, cost}` →
  - **sidebar:** feed line + thumbnail คลิกเปิดเต็ม (อ่านไฟล์จาก workspace ผ่าน [`files.py`](../daemon/routes/files.py))
  - **Godot:** เด้งรูปบน **hologram screen** เหนือหัว ET Artist ([`hologram_screen.gd`](../godot/scripts/hologram_screen.gd)) — โชว์ผลงานสด ๆ ในออฟฟิศ (เข้าธีม)
- รูปทั้งหมดสะสมใน `workspace/artwork/` → เปิดเป็นแกลเลอรีได้ภายหลัง

---

## 8. ET Artist role + preset

- เพิ่ม `ROLE_TOOL_PRESETS["artist"] = ["generate_image", "read_file", "write_file", "list_dir", "mkdir"]`
- role `.md` `roles/et-artist.md` (ไทย): หน้าที่ = แปลงโจทย์ CEO → prompt อังกฤษคุณภาพดี → generate_image → ตรวจ/ปรับ → ส่งงาน
- สมอง (chat) แนะนำ: local qwen หรือ cloud chat ที่แต่ง prompt เก่ง; image_model = Nano Banana (ฟรี) เป็นค่าเริ่ม

---

## 9. Edge cases

| กรณี | จัดการ |
|---|---|
| ไม่มี key สร้างภาพได้ | observation แนะนำเพิ่ม Gemini (ฟรี) — ไม่ throw |
| provider ไม่รองรับ image (เช่น GitHub Models) | ไม่โผล่ใน `?kind=image` (ไม่มี image-kind ใน cache) |
| โมเดลเสียเงิน + cost guard เกินเพดาน | block + แจ้งเตือน (เหมือน chat) |
| รูปใหญ่/หลายรูป | จำกัด n≤4 + ขนาดไฟล์ + timeout |
| prompt ผิดนโยบาย provider (เซฟตี้) | คืน error ของ provider เป็น observation ให้ agent ลองใหม่ |
| Nano Banana รับรูป input (แก้ภาพ/img2img) | v1 = text→image ก่อน; img2img (ใส่ `input_path`) = §12 ข้อเคาะ |

---

## 10. แตกงาน (M17-1 … M17-9)

| # | งาน | Tag |
|---|---|---|
| M17-1 | `image_adapter.py` — backend ต่อ provider (gemini nano/imagen, openai, openrouter) + `generate()` reuse `_resolve_cloud_key` | BE |
| M17-2 | `generate_image` ใน TOOLS_SPEC/execute — เซฟ workspace/artwork + WS event + summarize | BE |
| M17-3 | `AgentConfig.image_model` + resolve default ฟรี (Nano Banana) | BE |
| M17-4 | `/models/available?kind=image` (ขยาย M16) + ป้าย _price_tag | BE |
| M17-5 | permission gate + cost_guard per-image (ราคาประมาณ/รูป) | BE |
| M17-6 | UI Gear — ช่อง "🎨 Model สร้างภาพ" โผล่เมื่อเปิด tool + dropdown + key picker | UI |
| M17-7 | แสดงผล: WS `image.generated` → sidebar thumbnail + Godot hologram | UI+GODOT |
| M17-8 | ET Artist preset + `roles/et-artist.md` | BE |
| M17-9 | QA Gate M17 (offline mock adapter) | QA |

ลำดับ: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9

---

## 11. QA / Acceptance
- [ ] ET Artist (มี Gemini key) สั่ง "วาด …" → ได้ PNG ใน workspace/artwork + โชว์ใน sidebar/Godot
- [ ] เปลี่ยน image_model เป็น gpt-image-1 (paid) → permission เตือนราคา → สร้างได้
- [ ] ไม่มี key สร้างภาพ → ข้อความแนะนำ ไม่ crash
- [ ] cost_guard นับ per-image + เพดานทำงาน
- [ ] ช่อง "🎨 Model สร้างภาพ" โผล่เฉพาะเมื่อเปิด tool generate_image
- [ ] image_model แยกจากสมอง: สมอง local qwen + วาดด้วย Nano Banana ได้
- [ ] ของเดิมไม่พัง (tool อื่น/agent ที่ไม่มี image_model)

---

## 12. ข้อเสนอให้ CEO เคาะ (ผมแนะนำค่า default ไว้แล้ว)

1. **ขอบเขต v1:** เริ่ม **text→image ก่อน** (แนะนำ) แล้วค่อยเพิ่ม **img2img/แก้ภาพ** (Nano Banana รับรูป input ได้) ใน v2 — หรืออยากได้ img2img ตั้งแต่ v1 เลย?
2. **default image model:** = **Nano Banana (ฟรี)** เมื่อมี Gemini key (แนะนำ) — โอเคไหม
3. **แสดงผล:** **sidebar thumbnail + Godot hologram** (แนะนำ ทั้งคู่) หรือเอาแค่ไฟล์ใน workspace พอ
4. **permission:** บังคับ **ทุกครั้ง** สำหรับ generate_image (กันเงินรั่ว) — แนะนำใช่; หรือยกเว้นเมื่อเป็นโมเดลฟรี
5. **จำนวนรูป/ครั้ง:** default 1, สูงสุด 4 — โอเคไหม
6. **provider เริ่มต้น:** v1 รองรับ **Gemini (ฟรี) + OpenAI (paid)** ก่อน แล้วค่อยเพิ่ม OpenRouter/FLUX — หรือเอา OpenRouter มาตั้งแต่แรก?

> เคาะ 6 ข้อนี้แล้วผมเริ่ม M17-1 ได้ทันที (สร้าง branch + issues เหมือนรอบ M16)
