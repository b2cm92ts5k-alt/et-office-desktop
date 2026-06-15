"""A-4 / M6-2b placeholder character spritesheets — ตาม docs/ART-SPEC.md §3 เป๊ะ

แผ่นเต็ม v2: **192×528** = 6 cols (frame) × 11 rows, ช่องละ 32×48
  row 0-3  WALK  SE/SW/NE/NW (6 frame @ 8fps)
  row 4-7  IDLE  SE/SW/NE/NW (4 frame @ 4fps — หายใจ + กระพริบตา)
  row 8-9  SIT+TYPE SE/SW     (4 frame @ 6fps — พิมพ์งานที่โต๊ะ)
  row 10   SLEEP             (2 frame — ใช้ใน dorm)
ช่องที่เกินจำนวนเฟรมปล่อยโปร่งใส (engine เล่นเฉพาะเฟรมที่มีจริงตาม ROW_FRAMES ใน agent_sprite.gd)

งานวาดจริงแทนได้ 1:1: ชื่อไฟล์เดิม + layout เดิม → ไม่ต้องแก้โค้ด Godot
รัน: ../.venv/Scripts/python.exe gen_placeholder_chars.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).parent.parent / "godot" / "assets" / "sprites" / "characters"
OUT.mkdir(parents=True, exist_ok=True)

FRAME_W, FRAME_H = 32, 48
COLS = 6
ROWS = 11
WALK_F = 6
IDLE_F = 4
SIT_F = 4
SLEEP_F = 2

# role → (สีชุดหลัก จาก ART-SPEC, สีเข้มสำหรับ outline/ขา)
CHARS = {
    "producer": ((224, 64, 251), (96, 16, 160)),    # neon magenta
    "coder":    ((0, 229, 255), (0, 90, 110)),      # cyan
    "designer": ((255, 77, 166), (120, 20, 70)),    # hot pink
    "research": ((0, 255, 159), (0, 110, 70)),      # green
    "ceo":      ((255, 224, 64), (130, 100, 0)),    # gold
}
SKIN = (240, 200, 170)
HAIR = (40, 30, 60)
SCREEN = (0, 229, 255)  # จอที่ตัวละครพิมพ์ (cyan hologram)

# ลำดับก้าวขา 6 เฟรม (offset px ของขาซ้าย/ขวา สลับกัน)
STRIDE = [0, 2, 3, 2, 0, -2]


def _head(d: ImageDraw.ImageDraw, cx: int, oy: int, dark, facing_front: bool,
          mirror: bool, blink: bool = False) -> None:
    d.rectangle([cx - 5, oy + 8, cx + 5, oy + 19], fill=SKIN, outline=dark)
    d.rectangle([cx - 5, oy + 8, cx + 5, oy + 12], fill=HAIR)  # ผม
    if facing_front:  # SE/SW เห็นหน้า — มีตา
        ex = -1 if mirror else 0
        if blink:  # หลับตา = ขีดสั้น
            d.line([(cx - 3 + ex, oy + 15), (cx - 2 + ex, oy + 15)], fill=(20, 10, 30))
            d.line([(cx + 2 + ex, oy + 15), (cx + 3 + ex, oy + 15)], fill=(20, 10, 30))
        else:
            d.point([(cx - 3 + ex, oy + 15), (cx + 2 + ex, oy + 15)], fill=(20, 10, 30))
    else:  # NE/NW หันหลัง — ผมเต็มหัว
        d.rectangle([cx - 5, oy + 8, cx + 5, oy + 16], fill=HAIR)


def draw_walk(d: ImageDraw.ImageDraw, ox: int, oy: int,
              body, dark, facing_front: bool, mirror: bool, step: int) -> None:
    cx = ox + FRAME_W // 2
    # ขา 2 ข้าง — ก้าวสลับ
    lf, rf = STRIDE[step], STRIDE[(step + 3) % 6]
    if mirror:
        lf, rf = rf, lf
    d.rectangle([cx - 5, oy + 36 + min(0, lf), cx - 2, oy + 45 + abs(lf) // 2], fill=dark)
    d.rectangle([cx + 1, oy + 36 + min(0, rf), cx + 4, oy + 45 + abs(rf) // 2], fill=dark)
    # ตัว
    d.rectangle([cx - 7, oy + 20, cx + 6, oy + 36], fill=body, outline=dark)
    # แขน (แกว่งตามขาเล็กน้อย)
    d.rectangle([cx - 9, oy + 22 + lf // 2, cx - 7, oy + 33], fill=dark)
    d.rectangle([cx + 7, oy + 22 + rf // 2, cx + 9, oy + 33], fill=dark)
    _head(d, cx, oy, dark, facing_front, mirror)


def draw_idle(d: ImageDraw.ImageDraw, ox: int, oy: int,
              body, dark, facing_front: bool, mirror: bool, frame: int) -> None:
    """ยืนนิ่ง: หายใจ (ตัวขยับขึ้นลง 1px) + กระพริบตาเฟรมที่ 2"""
    cx = ox + FRAME_W // 2
    bob = (0, 1, 1, 0)[frame]          # หายใจเข้า-ออก
    blink = facing_front and frame == 2
    # ขายืนตรง 2 ข้าง
    d.rectangle([cx - 5, oy + 36, cx - 2, oy + 45], fill=dark)
    d.rectangle([cx + 1, oy + 36, cx + 4, oy + 45], fill=dark)
    # ตัว (ขยับลงตาม bob)
    d.rectangle([cx - 7, oy + 20 + bob, cx + 6, oy + 36], fill=body, outline=dark)
    # แขนแนบตัว
    d.rectangle([cx - 9, oy + 23 + bob, cx - 7, oy + 33], fill=dark)
    d.rectangle([cx + 7, oy + 23 + bob, cx + 9, oy + 33], fill=dark)
    _head(d, cx, oy + bob, dark, facing_front, mirror, blink)


def draw_sit(d: ImageDraw.ImageDraw, ox: int, oy: int,
             body, dark, mirror: bool, frame: int) -> None:
    """นั่งพิมพ์งาน (เห็นหน้า SE/SW): ตัวต่ำลง ขางอใต้โต๊ะ มือพิมพ์ขยับ + จอเรืองแสง"""
    cx = ox + FRAME_W // 2
    sit_y = 6                          # ทั้งตัวเลื่อนลง (นั่ง)
    # ขา/ต้นขางอแนวนอน (ใต้โต๊ะ)
    d.rectangle([cx - 6, oy + 38, cx + 5, oy + 44], fill=dark)
    # ตัว
    d.rectangle([cx - 7, oy + 22 + sit_y, cx + 6, oy + 38 + sit_y - 2], fill=body, outline=dark)
    _head(d, cx, oy + sit_y, dark, True, mirror)
    # จอ hologram เล็กตรงหน้า (ฝั่งที่หันไป)
    sx = cx + (6 if not mirror else -10)
    d.rectangle([sx, oy + 26, sx + 4, oy + 34], fill=(*SCREEN, 180))
    # มือพิมพ์ — ขยับขึ้นลงสลับเฟรม
    h1 = oy + 33 + sit_y + (frame % 2)
    h2 = oy + 33 + sit_y + ((frame + 1) % 2)
    d.rectangle([cx - 9, h1, cx - 6, h1 + 2], fill=SKIN)
    d.rectangle([cx + 6, h2, cx + 9, h2 + 2], fill=SKIN)


def draw_sleep(d: ImageDraw.ImageDraw, ox: int, oy: int,
               body, dark, frame: int) -> None:
    """หลับ: ฟุบ/เอนตัว ก้มหัว — 2 เฟรมหายใจเบา ๆ (Zzz วาดโดย engine)"""
    cx = ox + FRAME_W // 2
    bob = frame  # 0/1 หายใจ
    # ตัวเอนต่ำ (ก้ม)
    d.rectangle([cx - 7, oy + 30 + bob, cx + 6, oy + 44], fill=body, outline=dark)
    # หัวก้มลงด้านหน้า
    d.rectangle([cx - 5, oy + 24 + bob, cx + 5, oy + 33 + bob], fill=SKIN, outline=dark)
    d.rectangle([cx - 5, oy + 24 + bob, cx + 5, oy + 28 + bob], fill=HAIR)
    # ตาหลับ (ขีด)
    d.line([(cx - 2, oy + 30 + bob), (cx + 2, oy + 30 + bob)], fill=(20, 10, 30))


def make_sheet(body, dark) -> Image.Image:
    img = Image.new("RGBA", (FRAME_W * COLS, FRAME_H * ROWS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    dirs = [(True, False), (True, True), (False, False), (False, True)]  # SE,SW,NE,NW
    # WALK rows 0-3
    for row, (front, mirror) in enumerate(dirs):
        for col in range(WALK_F):
            draw_walk(d, col * FRAME_W, row * FRAME_H, body, dark, front, mirror, col)
    # IDLE rows 4-7
    for i, (front, mirror) in enumerate(dirs):
        row = 4 + i
        for col in range(IDLE_F):
            draw_idle(d, col * FRAME_W, row * FRAME_H, body, dark, front, mirror, col)
    # SIT rows 8-9 (SE, SW เท่านั้น)
    for i, mirror in enumerate([False, True]):
        row = 8 + i
        for col in range(SIT_F):
            draw_sit(d, col * FRAME_W, row * FRAME_H, body, dark, mirror, col)
    # SLEEP row 10
    for col in range(SLEEP_F):
        draw_sleep(d, col * FRAME_W, 10 * FRAME_H, body, dark, col)
    return img


def main() -> None:
    for name, (body, dark) in CHARS.items():
        make_sheet(body, dark).save(OUT / f"char_{name}.png")
    print(f"generated {len(CHARS)} spritesheets (192x528, 11 rows) -> {OUT}")


if __name__ == "__main__":
    main()
