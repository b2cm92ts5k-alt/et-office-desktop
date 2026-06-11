"""A-4 placeholder character spritesheets — ตาม docs/ART-SPEC.md เป๊ะ
192x192 ต่อตัว = 6 cols (walk frames) x 4 rows (SE, SW, NE, NW), frame 32x48

งานวาดจริงแทนได้ 1:1: ชื่อไฟล์เดิม + layout เดิม → ไม่ต้องแก้โค้ด Godot
รัน: ../.venv/Scripts/python.exe gen_placeholder_chars.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).parent.parent / "godot" / "assets" / "sprites" / "characters"
OUT.mkdir(parents=True, exist_ok=True)

FRAME_W, FRAME_H = 32, 48
COLS, ROWS = 6, 4  # walk 6 เฟรม x ทิศ SE,SW,NE,NW

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

# ลำดับก้าวขา 6 เฟรม (offset px ของขาซ้าย/ขวา สลับกัน)
STRIDE = [0, 2, 3, 2, 0, -2]


def draw_frame(d: ImageDraw.ImageDraw, ox: int, oy: int,
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
    # หัว
    d.rectangle([cx - 5, oy + 8, cx + 5, oy + 19], fill=SKIN, outline=dark)
    d.rectangle([cx - 5, oy + 8, cx + 5, oy + 12], fill=HAIR)  # ผม
    if facing_front:  # SE/SW เห็นหน้า — มีตา
        ex = -1 if mirror else 0
        d.point([(cx - 3 + ex, oy + 15), (cx + 2 + ex, oy + 15)], fill=(20, 10, 30))
    else:  # NE/NW หันหลัง — ผมเต็มหัว
        d.rectangle([cx - 5, oy + 8, cx + 5, oy + 16], fill=HAIR)


def make_sheet(body, dark) -> Image.Image:
    img = Image.new("RGBA", (FRAME_W * COLS, FRAME_H * ROWS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # rows: 0=SE (หน้า), 1=SW (หน้า mirror), 2=NE (หลัง), 3=NW (หลัง mirror)
    for row, (front, mirror) in enumerate([(True, False), (True, True),
                                           (False, False), (False, True)]):
        for col in range(COLS):
            draw_frame(d, col * FRAME_W, row * FRAME_H, body, dark, front, mirror, col)
    return img


def main() -> None:
    for name, (body, dark) in CHARS.items():
        make_sheet(body, dark).save(OUT / f"char_{name}.png")
    print(f"generated {len(CHARS)} spritesheets -> {OUT}")


if __name__ == "__main__":
    main()
