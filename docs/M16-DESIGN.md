# M16 — Dynamic Cloud Models & Provider Expansion (Design Spec)

> สถานะ: **📝 ออกแบบ (2026-06-20)** — รอ CEO เคาะเริ่มทำ
> เป้าหมาย: 1 API key ของ provider ไหน ก็ต้องเลือก model ได้ **ครบทุกตัวที่ key นั้นเปิดให้** (ไม่ใช่แค่ลิสต์ที่เราเขียนมือ) + เพิ่ม provider ใหม่ (OpenRouter, GitHub Models) ได้ง่าย
>
> **CEO เคาะแล้ว (2026-06-20):**
> 1. **Filter:** default โชว์เฉพาะ model ที่ใช้เป็นสมอง agent ได้ (chat) + ปุ่ม "แสดงทั้งหมด" — **ต้องกระชับใน Gear ของ agent (พื้นที่จำกัด ห้ามดูรก)**
> 2. **Scope:** รอบเดียว — refactor เป็น provider registry + เพิ่ม OpenRouter & GitHub Models
> 3. **Refresh:** ผู้ใช้กดอัปเดตเอง (ไม่ auto) + **แจ้งเตือนสั้น ๆ** ว่า "ลิสต์เก่าแล้ว / มี model ใหม่"

---

## 1. ปัญหา (จากที่ CEO เจอจริง)

ใส่ Google key 1 ตัว (เปิดได้ ~50+ model) ลงใน ET Office → **เลือกได้แค่ Gemini 3 ตัว**

ต้นตอ: ระบบมี **2 แหล่งข้อมูล model ที่ไม่คุยกัน** —

| จุด | ทำอะไร | ปัญหา |
|---|---|---|
| `validate_cloud_key()` — [`llm_adapter.py:175`](../daemon/adapters/llm_adapter.py) | ตอนเพิ่ม key ยิง `/v1/models` ของ provider → **ได้รายชื่อ model จริงครบทุกตัว** | ✅ ดึงครบอยู่แล้ว |
| `add_api_key_account()` — [`accounts.py:47`](../daemon/routes/accounts.py) | รับลิสต์นั้นมา → return ครั้งเดียว → **ไม่ persist** | ❌ ของดีหลุดมือ |
| `ProviderAccountStore` — [`account_store.py`](../daemon/services/account_store.py) | schema = `{id, provider, label, secret, ...}` | ❌ ไม่มีช่อง `models` |
| `GET /models/available` — [`models.py:71`](../daemon/routes/models.py) | cloud part ดึงจาก `cloud_models()` → **`CLOUD_CATALOG` ที่ hardcode มือ** | ❌ คือลิสต์ที่ CEO เห็น |

**สรุป:** dropdown อ่าน dict ที่เขียนมือ ([`llm_adapter.py:114`](../daemon/adapters/llm_adapter.py)) ทั้งที่เราดึงลิสต์จริงมาแล้วแต่โยนทิ้ง

ปัญหารอง: การเพิ่ม provider 1 ตัวต้องแก้ **5 dict กระจายกัน** — `ENV_KEY_MAP`, `DEFAULT_CLOUD_MODELS`, `LLM_PREFIX`, `CLOUD_BASE_URL`, `_VALIDATE_EP` → เพิ่ม OpenRouter/GitHub ทีต้องแตะ 5 ที่ ลืมง่าย

พื้นฐานที่ดีอยู่แล้ว (ไม่ต้องรื้อ): account_store เข้ารหัส DPAPI, การเลือก key/account แยกต่อ agent, cost_guard fallback ราคาเหมาเมื่อ model ไม่อยู่ใน catalog, tool-loop เสถียร

---

## 2. หลักการออกแบบ (พลิก source of truth)

```
เดิม:  dropdown ─reads─▶ CLOUD_CATALOG (เขียนมือ, ตายตัว)   ← คอขวด
ใหม่:  dropdown ─reads─▶ models ที่ persist บน account (ดึงจริงต่อ key)
                          └─ overlay ─▶ CLOUD_CATALOG (label สวย/ราคา/⭐แนะนำ)
```

3 เสาหลัก:

1. **Provider Registry** — ยุบ 5 dict เป็น **ตารางเดียว** `PROVIDERS` → เพิ่ม provider = เพิ่ม 1 entry
2. **Per-account model cache** — ลิสต์ที่ดึงจริง persist บน account (พร้อม classify ว่าเป็น chat/embed/image/...)
3. **Catalog → overlay** — `CLOUD_CATALOG` ไม่ใช่ตัวจำกัดอีก เป็นแค่ metadata เสริม (label ไทย, ราคา, ป้าย ⭐) ทับเมื่อ match id ได้

---

## 3. เสา A — Provider Registry (ยุบ 5 dict → 1 ตาราง)

ไฟล์ใหม่ `daemon/adapters/providers.py` (หรือต่อท้าย `llm_adapter.py`):

```python
# ProviderSpec: ทุกอย่างของ 1 provider อยู่ที่เดียว
PROVIDERS: dict[str, dict] = {
  "gemini": {
    "label": "Google Gemini",
    "env_key": "GOOGLE_API_KEY",
    "default_model": "gemini-2.5-flash",
    "route": {"kind": "litellm", "prefix": "gemini"},
    "list": {  # endpoint ดึงรายชื่อ model จริง
      "url": "https://generativelanguage.googleapis.com/v1beta/models?key={k}",
      "headers": lambda k: {},
      "parse": parse_gemini,   # → list[ModelInfo]
    },
  },
  "claude":   {... "route": {"kind": "litellm", "prefix": "anthropic"}, ...},
  "openai":   {... "route": {"kind": "litellm", "prefix": "openai"}, ...},
  "deepseek": {... "route": {"kind": "litellm", "prefix": "deepseek"}, ...},
  "grok":     {... "route": {"kind": "openai_compat",
                             "base_url": "https://api.x.ai/v1"}, ...},
  # ── ใหม่ M16 ──
  "openrouter": {
    "label": "OpenRouter",
    "env_key": "OPENROUTER_API_KEY",
    "default_model": "openai/gpt-4o-mini",
    "route": {"kind": "openai_compat", "base_url": "https://openrouter.ai/api/v1",
              "extra_headers": {"HTTP-Referer": "https://et-office.local",
                                "X-Title": "ET Office"}},
    "list": {"url": "https://openrouter.ai/api/v1/models",
             "headers": lambda k: {"Authorization": f"Bearer {k}"},
             "parse": parse_openrouter},   # มี pricing + context_length + modality มาด้วย!
  },
  "github": {
    "label": "GitHub Models",
    "env_key": "GITHUB_TOKEN",
    "default_model": "openai/gpt-4o",
    "route": {"kind": "openai_compat", "base_url": "https://models.github.ai/inference"},
    "list": {"url": "https://models.github.ai/catalog/models",
             "headers": lambda k: {"Authorization": f"Bearer {k}",
                                   "Accept": "application/vnd.github+json"},
             "parse": parse_github},
  },
}
```

ของเดิม 5 dict กลายเป็น **derived view** (เพื่อ backward-compat ฟังก์ชันที่เรียกอยู่):
```python
ENV_KEY_MAP        = {p: s["env_key"] for p, s in PROVIDERS.items()}
DEFAULT_CLOUD_MODELS = {p: s["default_model"] for p, s in PROVIDERS.items()}
```

> หมายเหตุ endpoint (ต้อง verify ตอนลงมือ): OpenRouter `/models` คืน `data[].{id,name,pricing.{prompt,completion},context_length,architecture.{input_modalities,output_modalities}}`. GitHub Models catalog endpoint และ inference base_url อาจปรับชื่อ — id ฝั่ง GitHub มักเป็น `<publisher>/<model>` เช่น `openai/gpt-4o`. ทั้งคู่เป็น **OpenAI-compatible** → route ผ่าน `openai_compat` เหมือน Grok

---

## 4. เสา B — Per-account model cache (data model)

### 4.1 schema ของ account (เพิ่มฟิลด์)
```jsonc
{
  "id": "...", "provider": "gemini", "label": "...", "auth_mode": "api_key",
  "secret": { "key": "..." },          // เดิม (เข้ารหัส DPAPI)
  "created_at": 1718...,
  // ── เพิ่ม M16 ──
  "models": [ ModelInfo, ... ],        // ลิสต์ที่ดึงจริง (normalize+classify แล้ว)
  "models_fetched_at": 1718...,        // ts ครั้งล่าสุดที่ดึง → ใช้เช็ก staleness
  "models_count": 53
}
```
> persist รวมกับไฟล์ account เดิม (เข้ารหัส DPAPI) — `models` ไม่ใช่ secret แต่ติดไปกับ blob ก็ไม่เสียหาย

### 4.2 ModelInfo (รูปร่างกลาง — normalize จากทุก provider)
```python
{
  "id": "gemini-2.5-flash",      # ส่งเข้า get_llm จริง
  "label": "Gemini 2.5 Flash",   # ชื่อโชว์ (จาก API ถ้ามี ไม่งั้น = id)
  "kind": "chat",                # chat | embed | image | audio | video | other
  "ctx": 1048576,                # context length (ถ้า provider บอก)
  "price_in": 0.0, "price_out": 0.0,   # USD/1M (ถ้า provider บอก เช่น OpenRouter)
}
```

### 4.3 classify — ตัวกรอง chat vs ไม่ใช่ chat
`classify_model(provider, raw) -> kind` ต่อ provider:
- **Gemini:** ดู `supportedGenerationMethods` → มี `generateContent` = `chat`; `embedContent` = `embed`; ชื่อ `veo*`=`video`, `imagen*`=`image`, `*-tts`/`lyria*`=`audio`
- **OpenRouter:** ดู `architecture.output_modalities` → `["text"]`=chat, `["image"]`=image ฯลฯ
- **OpenAI/GitHub/อื่น ๆ:** heuristic จาก id — `embedding`→embed, `whisper`/`tts`→audio, `dall-e`/`image`→image, นอกนั้น=chat

> **กฎความปลอดภัยของ filter:** classify ผิดได้ (เช่น chat model ใหม่ที่ id แปลก) → ปุ่ม **"แสดงทั้งหมด"** เป็นตาข่ายรองรับ ผู้ใช้ยังเลือก model ที่เราเดาผิดได้เสมอ ไม่มี dead-end

---

## 5. API changes

| Endpoint | เดิม/ใหม่ | ทำอะไร |
|---|---|---|
| `POST /accounts/api-key` | แก้ | หลัง validate สำเร็จ → normalize+classify `res.models` → **persist ลง account** (`models`, `models_fetched_at`) |
| `POST /accounts/{id}/refresh-models` | **ใหม่** | ดึง `/list` ของ provider ใหม่ด้วย key ของ account นั้น → อัปเดต cache → คืน diff `{added:[…], removed:[…], total}` |
| `GET /accounts/{id}/models?all=0` | **ใหม่** | คืน cache ของ account (default `chat` เท่านั้น; `all=1` = ทุก kind) — ใช้ตอน "แสดงทั้งหมด" |
| `GET /models/available` | **เขียนใหม่ (cloud part)** | union `models` ของทุก account ต่อ provider (เฉพาะ chat) → overlay catalog → 1 บรรทัด/model/provider |

### 5.1 `/models/available` — logic ใหม่ (cloud part)
```
สำหรับแต่ละ provider ที่มี credential (account หรือ .env):
  models = union(chat models จากทุก account ของ provider นี้)
  ถ้า models ว่าง (เช่น .env key ที่ไม่เคย validate / เพิ่มตอน offline):
      → fallback: lazy-fetch ครั้งเดียว (cache in-memory TTL) → ถ้ายังไม่ได้ ใช้ CLOUD_CATALOG เดิม
  overlay: ถ้า id ตรง CLOUD_CATALOG → ใช้ label ไทย + ป้าย ⭐ + ราคา (สวยกว่า raw id)
  dedup ตาม model id (หลาย key เห็น model ซ้ำ → บรรทัดเดียว; เลือก key แยกที่ m-key เหมือนเดิม)
```
> คงพฤติกรรมเดิม: **1 บรรทัด/model ต่อ provider** (ไม่คูณตามจำนวน key) — key เลือกแยกที่ dropdown `m-key`

### 5.2 routing — `get_llm()` ผ่าน registry
```python
spec = PROVIDERS[cfg.provider]; route = spec["route"]
if route["kind"] == "litellm":
    return LLM(model=f'{route["prefix"]}/{model}', api_key=key, **extra)
else:  # openai_compat (grok, openrouter, github)
    return LLM(model=model, api_key=key, base_url=route["base_url"],
               extra_headers=route.get("extra_headers"), **extra)
```
> OpenRouter/GitHub: model id มี vendor ในตัว (`anthropic/claude-...`) → ส่งตรง ไม่ใส่ prefix เพิ่ม

### 5.3 ราคา — `cost_guard` / `cloud_price`
ลำดับ fallback (ขยายของเดิม): **ราคาใน account cache (OpenRouter มีให้)** → `CLOUD_CATALOG` → เหมา per-provider (`PRICE_PER_MTOK`) → ไม่มีก็ 0 (ไม่ crash) — cost_guard เดิมรองรับ fallback อยู่แล้ว แค่เพิ่มชั้นแรก

---

## 6. UI — ออกแบบให้กระชับใน Gear (โจทย์ CEO)

### 6.1 Gear ของ agent (`openModelPicker` → `m-model`) — พื้นที่จำกัด
ปัญหา: select เดียว 50+ บรรทัด = รก. ดีไซน์:

```
┌─ Model ────────────────────────────────┐
│ [ ⭐ Gemini 2.5 Flash · 🟢 free    ▾ ]  │  ← select เดียว, default = chat only
│ 🔌 แสดง model ทั้งหมด (53)               │  ← link เล็ก ใต้ select
└─────────────────────────────────────────┘
```
- **select ใช้ `<optgroup>`** จัดกลุ่มให้ตัวดีลอยบน — กันรก:
  - `⭐ แนะนำ` (ตัวที่ overlay catalog match — curated)
  - `💬 ใช้กับ agent ได้` (chat ที่เหลือ)
- กด **"แสดงทั้งหมด (N)"** → re-populate เพิ่มกลุ่ม:
  - `🧩 เฉพาะทาง (เลือกไม่ได้)` — embeddings/วิดีโอ/เสียง แสดงแบบ `disabled` + dim (โชว์ครบตามที่ CEO อยากเห็น แต่กันเผลอเลือกมาเป็นสมอง agent)
- ถ้าลิสต์ chat ยังยาว → โผล่ช่อง **พิมพ์กรอง** (combobox) เฉพาะตอนเปิด "แสดงทั้งหมด" — ปกติซ่อนไว้ ไม่กินที่
- คง `m-key` dropdown (เลือก key/บัญชี) ไว้เหมือนเดิม ใต้ `m-model`

> สรุป Gear = **1 select + 1 link** เป็น default (เท่าเดิม) ความซับซ้อนซ่อนหลัง toggle — ไม่รกขึ้น

### 6.2 Settings → Keys (พื้นที่เยอะกว่า) — refresh + แจ้งเตือน
ต่อ 1 account แสดง:
```
[gemini]  my-google  …aBc9   53 model   🔄 รีเฟรช   ✕ ลบ
          └ ⚠️ ลิสต์อาจเก่า (ดึงเมื่อ 18 วันก่อน) — กดรีเฟรช
```
- ปุ่ม **🔄 รีเฟรช** → `POST /accounts/{id}/refresh-models` → toast ผลลัพธ์
- **แจ้งเตือน (ตามมติ CEO ข้อ 3):**
  - **staleness:** ถ้า `models_fetched_at` เก่ากว่า ~14 วัน → ชิปเตือนจาง ๆ "ลิสต์อาจเก่า — รีเฟรช"
  - **มี model ใหม่:** ทราบได้หลังกดรีเฟรชเท่านั้น (เทียบ diff) → ถ้า `added > 0` เด้ง toast "พบ N model ใหม่จาก {provider} 🆕"
  > ตรงไปตรงมา: ระบบ "รู้ว่ามีรุ่นใหม่" ก็ต่อเมื่อ fetch — เราจึงเตือนแบบ (ก) เวลาเก่า + (ข) สรุป diff หลังรีเฟรช ไม่แอบยิง network เอง (ตรงกับ "ผู้ใช้กดเอง")

### 6.3 provider chips ไม่ hardcode
`key-status` ([`app.js:745`](../sidebar/web/app.js)) ตอนนี้ fix `["claude","gemini","openai","grok","deepseek"]` → เปลี่ยนเป็น loop จาก `/accounts` field `providers` (มาจาก registry) → OpenRouter/GitHub โผล่อัตโนมัติ

---

## 7. Edge cases

| กรณี | จัดการ |
|---|---|
| .env key (ไม่มี account ให้ cache) | lazy-fetch in-memory (TTL) ครั้งแรกที่ `/models/available` ต้องใช้ → offline ก็ fallback `CLOUD_CATALOG` |
| เพิ่ม key ตอน offline / validate fail | เก็บ account ได้ (models ว่าง + flag) → dropdown ใช้ catalog fallback → ปุ่มรีเฟรชค่อยลองใหม่ |
| model ไม่อยู่ catalog เลย | โชว์ raw id เป็น label, ไม่มี ⭐, ราคา = fallback เหมา per-provider |
| classify ผิด (chat โดนซ่อน) | "แสดงทั้งหมด" กู้คืนได้เสมอ — ไม่มี dead-end |
| OpenRouter ต้องการ header `HTTP-Referer`/`X-Title` | ใส่ใน `route.extra_headers` ของ registry |
| key เดียว provider เดียว 50+ ตัว | `/models/available` กรอง chat → ลิสต์สั้นลงมาก; ตัวเต็มอยู่หลัง toggle |

---

## 8. แตกงาน (Tasks M16-1 … M16-9)

| # | งาน | ผล |
|---|---|---|
| **M16-1** | Provider Registry — ยุบ 5 dict → `PROVIDERS`, ทำ derived view (ENV_KEY_MAP ฯลฯ) | refactor ล้วน, ของเดิมไม่พัง |
| **M16-2** | `parse_*` + `classify_model` ต่อ provider (normalize → ModelInfo) | มี unit test ต่อ provider |
| **M16-3** | account_store: เก็บ `models`/`models_fetched_at` + `refresh-models` + `GET …/models` | cache persist |
| **M16-4** | เขียน `/models/available` cloud part ใหม่ (union + overlay + dedup + fallback) | dropdown = dynamic |
| **M16-5** | `get_llm` + `cloud_price` route ผ่าน registry | รองรับ openai_compat ใหม่ |
| **M16-6** | เพิ่ม entry OpenRouter + GitHub Models (env/route/list/parse) | 2 provider ใหม่ใช้ได้ |
| **M16-7** | UI Gear: optgroup + "แสดงทั้งหมด" toggle + combobox กรอง (กระชับ) | ไม่รกขึ้น |
| **M16-8** | UI Settings: ปุ่มรีเฟรช + ชิป staleness + toast diff + chips จาก registry | แจ้งเตือนตามมติ |
| **M16-9** | QA checklist | acceptance ผ่าน |

ลำดับแนะนำ: 1 → 2 → 3 → 5 → 4 → 6 → 7 → 8 → 9 (วาง backend/registry ให้นิ่งก่อนค่อยต่อ UI)

---

## 9. QA / Acceptance (M16-9)

- [ ] เพิ่ม Google key → dropdown โชว์ Gemini chat **ครบทุกรุ่น** (ไม่ใช่ 3) — ไม่มี embeddings/Veo/Lyra ปนใน default
- [ ] กด "แสดงทั้งหมด" → เห็น embeddings/วิดีโอ/เสียง จัดกลุ่ม `disabled` (โชว์ครบ แต่เลือกเป็นสมองไม่ได้)
- [ ] เพิ่ม OpenRouter key → เลือก model ข้ามค่าย (Llama/DeepSeek/Claude…) ได้ → agent รันผ่าน openai_compat จริง
- [ ] เพิ่ม GitHub Models token → เลือก `openai/gpt-4o` ฯลฯ → รันได้
- [ ] กดรีเฟรช account → count อัปเดต + toast diff เมื่อมีตัวใหม่
- [ ] เพิ่ม key ตอน offline → ไม่ crash, fallback catalog, รีเฟรชภายหลังได้
- [ ] cost_guard บันทึกค่าใช้จ่าย model dynamic (ใช้ราคา cache/catalog/เหมา ตามลำดับ)
- [ ] Gear ยังดู **กระชับเท่าเดิม** (default = 1 select + 1 link)
- [ ] ของเดิมไม่พัง: agent ที่ตั้ง model claude/gemini ไว้ก่อน M16 ยังทำงาน

---

## 10. นอกขอบเขต (ไว้เวอร์ชันหน้า)
- auto-refresh ตามเวลา (รอบนี้ผู้ใช้กดเอง — มติ CEO)
- จัดอันดับ/แนะนำ model อัตโนมัติตามงาน (ขยายจาก `SPECIALIST_PRESETS`)
- provider ที่ไม่ใช่ OpenAI-compatible และไม่มีใน litellm (ถ้ามีในอนาคต ต้องเพิ่ม `route.kind` ใหม่)
- กรอง model ตามราคา/context length ใน UI (filter ขั้นสูง)
