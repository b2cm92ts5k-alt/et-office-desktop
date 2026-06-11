# วิธีเปลี่ยน Asset / Sprite (Asset Swap Guide)

> Placeholder ทุกชิ้นถูกออกแบบให้**แทนที่ได้ 1:1** — วางไฟล์ชื่อเดิมทับ แล้วเปิด Godot ใหม่ จบ
> สเปคขนาด/เลย์เอาต์ทั้งหมดอยู่ใน [ART-SPEC.md](ART-SPEC.md)

## เปลี่ยน sprite ตัวละคร

1. วาดตามสเปค: **192×192 px** = 6 คอลัมน์ (เฟรมเดิน) × 4 แถว (ทิศ **SE, SW, NE, NW** บนลงล่าง) เฟรมละ 32×48
2. Export เป็น PNG (RGBA) ชื่อไฟล์เดิม:
   - `char_producer.png` `char_coder.png` `char_designer.png` `char_research.png` `char_ceo.png`
3. วางทับที่ `godot/assets/sprites/characters/`
4. เปิดโปรเจคใน Godot editor หนึ่งครั้ง (auto reimport) — หรือรัน `godot --headless --import`

**เพิ่มตัวละครใหม่:** ตั้งชื่อ `char_<key>.png` แล้วเพิ่ม keyword → key ใน `ROLE_SPRITES` ที่ [agent_manager.gd](../godot/scripts/agent_manager.gd) (จุดเดียวที่ map role → ไฟล์)

## เปลี่ยน tiles / ผนัง

วางทับชื่อเดิมที่ `godot/assets/sprites/furniture/`:
`tile_floor_a.png` `tile_floor_b.png` (64×32) · `wall_n.png` `wall_w.png` (64×96)

## เปลี่ยน speech bubble (hologram)

วางทับชื่อเดิมที่ `godot/assets/sprites/fx/`: `bubble_9patch.png` (24×24, 9-patch margin 8px ทุกด้าน)
ถ้าเปลี่ยนขนาด/margin แก้ const หัวไฟล์ [hud.gd](../godot/scripts/hud.gd) (`BUBBLE_MARGIN`, `BUBBLE_WIDTH`)
Regenerate placeholder: `.venv\Scripts\python.exe art-src\gen_placeholder_ui.py`

## ถ้าจะเปลี่ยน "เลย์เอาต์" spritesheet (ไม่ใช่แค่รูป)

ค่าคงที่ทั้งหมดอยู่หัวไฟล์ [agent_sprite.gd](../godot/scripts/agent_sprite.gd) ที่เดียว:

```gdscript
const FRAME_COLS := 6   # จำนวนเฟรมเดิน
const FRAME_ROWS := 4   # จำนวนทิศ
const WALK_FPS := 8.0   # ความเร็วอนิเมชัน
```

## Regenerate placeholder (ถ้าอยากกลับมาใช้ของเดิม)

```powershell
.venv\Scripts\python.exe art-src\gen_placeholder_tiles.py
.venv\Scripts\python.exe art-src\gen_placeholder_chars.py
```

## กฎที่ต้องรักษาเสมอ (จาก ART-SPEC)

- Origin ตัวละคร = กึ่งกลางฐาน (เท้า) — โค้ดตั้ง offset ให้อัตโนมัติจากขนาดภาพ
- Import setting: Filter **Nearest** (โค้ดบังคับให้แล้วผ่าน `texture_filter`)
- Palette ตาม ART-SPEC §2 + brightness รวม ≤60%
- เก็บไฟล์ต้นฉบับ (.aseprite/.psd) ไว้ใน `art-src/` — โฟลเดอร์นี้ไม่ถูก Godot import
