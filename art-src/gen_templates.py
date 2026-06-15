"""A-9 swap templates — สร้าง 'แผ่นแม่แบบ' ให้ผู้ใช้วาด asset เองแล้วสลับเข้าได้ 1:1

ออก 3 ไฟล์ที่ art-src/templates/ :
  char_sheet_template.png  — แผ่นตัวละคร 192x528 ติดกริด+ป้ายท่า/ทิศต่อแถว
  furniture_guide.png      — ผังเฟอร์นิเจอร์/props ทุกชิ้น: กล่องขนาดจริง + ชื่อไฟล์ + ขนาด
  tile_guide.png           — floor diamond 64x32 + wall 64x96 พร้อมป้าย
วิธีใช้: เปิดใน Aseprite/โปรแกรมวาด → วาดทับช่อง → ลบ layer แม่แบบ → export ชื่อ/ขนาดเดิม
รัน: ../.venv/Scripts/python.exe gen_templates.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).parent / "templates"
OUT.mkdir(parents=True, exist_ok=True)

CYAN = (0, 229, 255, 220)
GRID = (74, 48, 128, 150)
DIM = (10, 8, 20, 90)
FILL = (42, 31, 78, 50)

CELL_W, CELL_H = 32, 48
CHAR_ROWS = [
    ("WALK SE", 6), ("WALK SW", 6), ("WALK NE", 6), ("WALK NW", 6),
    ("IDLE SE", 4), ("IDLE SW", 4), ("IDLE NE", 4), ("IDLE NW", 4),
    ("SIT SE", 4), ("SIT SW", 4), ("SLEEP", 2),
]

# (ชื่อไฟล์, w, h) — ตรง ART-SPEC §4 + gen_furniture.py
FURNITURE = [
    ("desk_agent", 64, 64), ("desk_ceo", 64, 64), ("chair", 32, 40),
    ("table_meeting", 128, 80), ("board_whiteboard", 96, 64),
    ("machine_coffee", 32, 48), ("rack_server", 48, 96), ("bed_bunk", 64, 80),
    ("plant_a", 32, 48), ("plant_b", 32, 48),
]


def char_sheet():
    img = Image.new("RGBA", (CELL_W * 6, CELL_H * 11), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for row, (label, used) in enumerate(CHAR_ROWS):
        for col in range(6):
            x0, y0 = col * CELL_W, row * CELL_H
            box = [x0, y0, x0 + CELL_W - 1, y0 + CELL_H - 1]
            if col >= used:
                d.rectangle(box, fill=DIM)
                d.line([x0, y0, x0 + CELL_W - 1, y0 + CELL_H - 1], fill=GRID)
            elif (row + col) % 2 == 0:
                d.rectangle(box, fill=FILL)
            d.rectangle(box, outline=GRID)
        d.text((2, row * CELL_H + 1), label, fill=CYAN)
    img.save(OUT / "char_sheet_template.png")


def _slot(d, x, y, w, h, name):
    """กล่องขนาดจริง + กริด + ชื่อ+ขนาด — ให้ผู้ใช้รู้ว่าต้องวาดในกรอบเท่าไหร่"""
    d.rectangle([x, y, x + w - 1, y + h - 1], fill=FILL, outline=CYAN)
    for gx in range(x, x + w, 8):
        d.line([gx, y, gx, y + h - 1], fill=(74, 48, 128, 50))
    for gy in range(y, y + h, 8):
        d.line([x, gy, x + w - 1, gy], fill=(74, 48, 128, 50))
    d.line([x + w // 2, y + h - 4, x + w // 2, y + h - 1], fill=(255, 224, 64, 220))  # mark origin (ฐานกลาง)
    d.text((x, y - 11), f"{name}.png  {w}x{h}", fill=CYAN)


def furniture_guide():
    pad, gap, top = 14, 26, 22
    cols = 3
    cw = max(w for _, w, _ in FURNITURE) + gap
    ch = max(h for _, _, h in FURNITURE) + gap
    rows = (len(FURNITURE) + cols - 1) // cols
    img = Image.new("RGBA", (pad * 2 + cols * cw, top + rows * ch + pad), (10, 8, 20, 255))
    d = ImageDraw.Draw(img)
    d.text((pad, 6), "ET OFFICE - Furniture/Prop swap guide (draw inside box, gold dot = base origin)", fill=CYAN)
    for i, (name, w, h) in enumerate(FURNITURE):
        cx = pad + (i % cols) * cw
        cy = top + (i // cols) * ch + 12
        _slot(d, cx, cy, w, h, name)
    img.save(OUT / "furniture_guide.png")


def tile_guide():
    img = Image.new("RGBA", (220, 150, ), (10, 8, 20, 255))
    d = ImageDraw.Draw(img)
    d.text((8, 6), "Floor 64x32 / Wall 64x96 (diamond 2:1)", fill=CYAN)
    # floor diamond
    fx, fy = 20, 40
    d.polygon([(fx + 32, fy), (fx + 63, fy + 16), (fx + 32, fy + 31), (fx, fy + 16)], outline=CYAN, fill=FILL)
    d.text((fx, fy + 34), "tile_floor_a/b 64x32", fill=CYAN)
    # wall
    wx, wy = 120, 30
    d.polygon([(wx, wy + 16), (wx + 32, wy + 32), (wx + 32, wy + 96), (wx, wy + 80)], outline=CYAN, fill=FILL)
    d.text((wx - 8, wy + 100), "wall_n/w 64x96", fill=CYAN)
    img.save(OUT / "tile_guide.png")


def main():
    char_sheet()
    furniture_guide()
    tile_guide()
    print(f"generated 3 templates -> {OUT}")


if __name__ == "__main__":
    main()
