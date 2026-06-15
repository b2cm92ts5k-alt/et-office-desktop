# ET Office — คู่มือสลับ Sprite Asset เอง (A-9)

> เป้าหมาย: เปลี่ยนรูป asset ทุกชิ้นเองได้แบบ **drop-in** — ไม่ต้องแก้โค้ด
> หลักการเดียว: **ชื่อไฟล์เดิม + ขนาดเดิม + PNG (RGBA) + Filter=Nearest** แล้ววางทับไฟล์เดิม

ทุก asset ที่มีตอนนี้เป็น **placeholder** ที่ generate ด้วย Pillow (`art-src/gen_*.py`)
ตามสเปคใน [`ART-SPEC.md`](ART-SPEC.md) เป๊ะ — วาดของจริงทับได้เลย

---

## วิธีสลับ (3 ขั้น)

1. เปิด **แม่แบบ** ที่ `art-src/templates/` (หรือโหลด char template จากปุ่มในหน้า Hire)
2. วาดทับในกรอบ (เก็บขนาด/origin เดิม — **จุดทอง = กึ่งกลางฐาน** ที่ตัวละคร/ของจะยืน)
3. Export เป็น PNG **ชื่อ+ขนาดเดิม** → วางทับไฟล์ใน `godot/assets/sprites/<หมวด>/`
   → เปิด Godot จะ import เอง (ตั้ง Filter=**Nearest**, Mipmaps off, Lossless)

> โทนสีต้องอยู่ใน **palette ที่ล็อกไว้** (ART-SPEC §2) + ความสว่างรวมฉาก ≤ 60%
> (neon ใช้เป็น accent เส้น/ขอบเล็ก ๆ ไม่ใช่พื้นที่ใหญ่ — ไม่งั้นแย่ง desktop icon)

---

## แม่แบบ (templates) ที่ให้มา — `art-src/templates/`

| ไฟล์ | ใช้กับ |
|---|---|
| `char_sheet_template.png` (192×528) | ตัวละคร — กริด + ป้ายท่า/ทิศต่อแถว |
| `furniture_guide.png` | เฟอร์นิเจอร์/props ทุกชิ้น — กล่องขนาดจริง + ชื่อไฟล์ + ขนาด + จุด origin |
| `tile_guide.png` | floor/wall diamond + ขนาด |

สร้างใหม่ได้ตลอด: `art-src/.venv/Scripts/python.exe gen_templates.py`

---

## หมวด asset + ขนาด (ชื่อไฟล์ = key สลับ)

### 1) Character Sheet — `godot/assets/sprites/characters/`
ช่องละ **32×48**, 6 คอลัมน์. รองรับ 2 ขนาด:
- **192×192** = เดินอย่างเดียว (4 แถว: WALK SE/SW/NE/NW)
- **192×528** = ครบทุกท่า (เพิ่ม IDLE×4, SIT SE/SW, SLEEP)

| ไฟล์ | role |
|---|---|
| `char_producer.png` `char_coder.png` `char_designer.png` `char_research.png` | ทีมงาน |
| `char_ceo.png` | CEO (โทนทอง) |

> per-agent: อัปโหลด sheet เฉพาะตัวผ่านหน้า **Hire** ได้ (M6-2) — เก็บแยก ไม่ทับ default

### 2) Furniture / Prop — `godot/assets/sprites/furniture/`
| ไฟล์ | ขนาด | ไฟล์ | ขนาด |
|---|---|---|---|
| `desk_agent.png` | 64×64 | `rack_server.png` | 48×96 |
| `desk_ceo.png` | 64×64 | `bed_bunk.png` | 64×80 |
| `chair.png` | 32×40 | `machine_coffee.png` | 32×48 |
| `table_meeting.png` | 128×80 | `plant_a.png` | 32×48 |
| `board_whiteboard.png` | 96×64 | `plant_b.png` | 32×48 |

สร้างใหม่: `gen_furniture.py`

### 3) Floor / Wall (tiles) — `godot/assets/sprites/furniture/`
| ไฟล์ | ขนาด | หมายเหตุ |
|---|---|---|
| `tile_floor_a.png` `tile_floor_b.png` | 64×32 | diamond dimetric 2:1 |
| `wall_n.png` `wall_w.png` | 64×96 | ผนังขวา/ซ้าย |
| `sign_etoffice.png` | 160×48 | ป้ายเรืองแสง |

สร้างใหม่: `gen_tiles.py` (เดิม `gen_placeholder_tiles.py`)

---

## ข้อควรระวัง
- **ห้าม** เปลี่ยนชื่อไฟล์/ขนาด — โค้ด Godot + uploader อิงค่านี้
- **ห้าม JPEG** — ต้อง PNG 32-bit (RGBA) เท่านั้น (ART-SPEC §6)
- origin ทุกชิ้น = **กึ่งกลางฐาน** (z-sort by grid_y+grid_x ถึงจะถูก)
- aura ของตัวละคร Godot วาดเอง (`neon_aura.gd`) — **อย่าวาดวงแสงลงใน sprite**
