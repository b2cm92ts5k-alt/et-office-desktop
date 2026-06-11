# ET Office Desktop — Pixel Art Specification (A-1)

> Single source of truth สำหรับ asset ทุกชิ้น — อ้างอิงจาก Design Doc §03 (Visual Design System)
> สไตล์: **Cyberpunk Synthwave 2.5D Isometric Pixel Art**

---

## 1. Grid & Projection

| ค่า | สเปค | เหตุผล |
|---|---|---|
| Projection | **Dimetric 2:1** (isometric แบบเกม) | มาตรฐาน pixel iso — เส้นทแยง 26.57° ไม่มี jaggies |
| Base tile | **64 × 32 px** (กว้าง × สูง) | ละเอียดพอใส่ detail neon, ไม่ใหญ่เกินจน office ล้นจอ |
| Wall height | 96 px (3 ชั้น tile) | ผนังสูงพอติด neon sign |
| Render scale | **2×** ใน Godot (integer scaling เท่านั้น) | คมแบบ pixel art บน 1080p — ห้าม scale เศษส่วน |
| Office footprint | ~20 × 14 tiles | ครอบ 6 zones พอดีบนจอ 1920×1080 ที่ scale 2× |
| Z-sort | sort by (grid_y + grid_x) | ตรงกับ M2-6 — กำหนดตั้งแต่วาด: origin ของ sprite = จุดกึ่งกลางฐาน |

## 2. Color Palette (LOCKED — ห้ามเพิ่มสีนอก palette)

### Core
| ชื่อ | Hex | ใช้กับ |
|---|---|---|
| BG Deep | `#07050F` | พื้นหลังนอกอาคาร, ความมืดฐาน |
| Panel Dark | `#0E0A1E` | พื้น tile หลัก |
| Panel Mid | `#140F28` | ผนัง, เฟอร์นิเจอร์เฉดมืด |
| Border | `#2A1F4E` | เส้นขอบ, รอยต่อ tile |
| Border Light | `#4A3080` | ขอบรับแสง |

### Neon (สีเรืองแสง — ใช้กับ emission layer เท่านั้น)
| ชื่อ | Hex | Zone / Role |
|---|---|---|
| Neon Magenta | `#E040FB` | **Producer aura**, ป้าย ET OFFICE |
| Cyan | `#00E5FF` | **Coder aura**, Ops floor, hologram |
| Hot Pink | `#FF4DA6` | **Designer aura**, Meeting room |
| Green | `#00FF9F` | **Research aura**, status OK |
| Yellow Gold | `#FFE040` | Exec/CEO zone |
| Orange | `#FF6030` | Cafe zone, BREAK |
| Blue | `#4080FF` | Dorm ambient |
| Purple | `#B060F0` | Server room |

### กฎ Brightness (สำคัญที่สุด — จาก Design Doc)
- **ความสว่างรวมของฉาก ≤ 60%** — wallpaper ต้องไม่แย่ง attention จาก desktop icon
- สี neon ใช้เป็น **accent เล็ก ๆ** (เส้น, ขอบ, จุด) ไม่ใช่พื้นที่ใหญ่
- พื้นที่ >70% ของภาพต้องเป็นเฉด dark (BG Deep → Border)
- ทดสอบ: ดู thumbnail ขาวดำ — ถ้าอ่าน icon ขาวบนภาพไม่ออก = สว่างเกิน

## 3. Characters (Agent Sprites)

| ค่า | สเปค |
|---|---|
| Canvas | **32 × 48 px** ต่อ frame |
| Origin | กึ่งกลางแนวนอน, ล่างสุด (เท้า) |
| ทิศทาง | 4 ทิศ: SE, SW, NE, NW (แถวละทิศใน spritesheet) |
| Walk | 6 frames / ทิศ @ 8 fps |
| Idle | 4 frames / ทิศ @ 4 fps (หายใจ, กระพริบตา) |
| Sit + type | 4 frames เฉพาะ SE, SW @ 6 fps |
| Sleep | 2 frames (ใช้ใน dorm) |
| Outline | 1px สีเข้มกว่าเสื้อผ้า 2 step — ไม่ใช้ดำสนิท |
| เอกลักษณ์ role | สีชุด + accessory: Producer=headset, Coder=แว่น, Designer=ผ้ากันเปื้อน/ปากกา, Research=แท็บเล็ต |
| Aura ring | **ไม่วาดใน sprite** — Godot วาดเอง (neon_aura.gd) |

**Spritesheet layout ต่อ 1 ตัวละคร:** แถว = ทิศ (SE,SW,NE,NW), คอลัมน์ = frame → ไฟล์เดียว `char_<role>.png` ขนาด 192×192 px (6 cols × 4 rows)

## 4. Furniture & Props

| ชิ้น | ขนาด (px) | จำนวน | หมายเหตุ |
|---|---|---|---|
| Desk + จอ | 64×64 | 7 (CEO 1 แบบพิเศษ) | จอเป็น layer แยกให้ hologram_screen.gd สลับ animation |
| เก้าอี้ | 32×40 | 8 | แยกชิ้นจาก desk เพื่อ z-sort ตัวละครนั่ง |
| โต๊ะประชุมกลม | 128×80 | 1 | กลาง meeting room |
| Whiteboard hologram | 96×64 | 1 | frame ว่าง — เนื้อหา render runtime |
| Coffee machine | 32×48 | 1 | neon orange glow |
| Server rack | 48×96 | 3 | LED แยก layer ให้กระพริบตาม LLM load |
| Bunk bed | 64×80 | 2 | dorm |
| ป้าย "ET OFFICE" | 160×48 | 1 | ตัวอักษร glow แยก layer สำหรับ flicker |
| ต้นไม้/ของตกแต่ง | 32×48 | 4-6 | เติมความมีชีวิต |

## 5. FX Flipbooks (A-5)

ทั้งหมด **32×32 px, 8 frames @ 12 fps**, canvas โปร่งใส:
`fx_done` ✅ · `fx_error` ❌ · `fx_proposal` 💡 · `fx_working` ⚡ · `fx_zzz` 💤

## 6. ไฟล์ & Naming Convention

```
godot/assets/sprites/
├── characters/char_producer.png      (192×192 spritesheet)
│              char_coder.png  char_designer.png  char_research.png  char_ceo.png
├── furniture/  tile_floor_a.png  tile_floor_b.png  wall_n.png  wall_w.png
│              desk_agent.png  desk_ceo.png  chair.png  table_meeting.png
│              rack_server.png  bed_bunk.png  machine_coffee.png  sign_etoffice.png
└── fx/         fx_done.png  fx_error.png  fx_proposal.png  fx_working.png  fx_zzz.png
```

- ชื่อไฟล์: `snake_case`, ภาษาอังกฤษ, มี prefix ตามชนิด (`char_`, `tile_`, `fx_`)
- PNG 32-bit (RGBA), ไม่ใช้ JPEG เด็ดขาด
- Aseprite: เก็บ .aseprite ต้นฉบับใน `art-src/` (นอก godot/ — ไม่ถูก import)
- Export: File > Export Sprite Sheet → By Rows, ไม่มี padding, ไม่ trim

## 7. Godot Import Settings (ทุก sprite)

- Filter: **Nearest** (ห้าม Linear — จะเบลอ)
- Mipmaps: off
- Compression: Lossless

## 8. ลำดับการผลิต (ตาม dependency บน board)

1. **A-2** tiles (floor 2 แบบ + wall 2 ด้าน) → ปลดบล็อค M2-7
2. **A-4** char_producer ตัวแรก (ครบ 4 ทิศ) → ปลดบล็อค M3-1 แล้วค่อยตามด้วยอีก 4 ตัว
3. **A-3** desk + chair ก่อน (agent ต้องมีที่นั่ง) → ที่เหลือทยอย
4. **A-5/A-6** FX + speech bubble — หลังสุดได้
