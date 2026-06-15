"""A-3 furniture + props — generate ครบชุดตาม docs/ART-SPEC.md §4 (dimetric 2:1)

ชื่อไฟล์/ขนาดตรงสเปคเป๊ะ → ผู้ใช้วาดเองแทนได้ 1:1 (ดู docs/ASSET-GUIDE.md)
origin ของทุกชิ้น = กึ่งกลางฐาน (bottom-center ของ canvas) ให้ z-sort ตรง
รัน: ../.venv/Scripts/python.exe gen_furniture.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).parent.parent / "godot" / "assets" / "sprites" / "furniture"
OUT.mkdir(parents=True, exist_ok=True)

# palette (LOCKED — ART-SPEC §2)
PANEL_DARK = (14, 10, 30, 255)
PANEL_MID = (20, 15, 40, 255)
BORDER = (42, 31, 78, 255)
BORDER_LIGHT = (74, 48, 128, 255)
CYAN = (0, 229, 255, 255)
MAGENTA = (224, 64, 251, 255)
PINK = (255, 77, 166, 255)
GREEN = (0, 255, 159, 255)
GOLD = (255, 224, 64, 255)
ORANGE = (255, 96, 48, 255)
PURPLE = (176, 96, 240, 255)


def _canvas(w, h):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def box(d, cx, by, bw, bh, h, top, left, right, edge=BORDER):
    """cuboid dimetric — (cx,by)=กึ่งกลางฐาน, bw/bh=diamond footprint, h=สูง px"""
    hw, hh = bw // 2, bh // 2
    bN, bE, bS, bW = (cx, by - bh), (cx + hw, by - hh), (cx, by), (cx - hw, by - hh)
    tN, tE, tS, tW = (cx, by - bh - h), (cx + hw, by - hh - h), (cx, by - h), (cx - hw, by - hh - h)
    d.polygon([bW, bS, tS, tW], fill=left, outline=edge)   # หน้าซ้าย
    d.polygon([bS, bE, tE, tS], fill=right, outline=edge)  # หน้าขวา
    d.polygon([tN, tE, tS, tW], fill=top, outline=edge)    # หน้าบน
    return (tN, tE, tS, tW)  # คืน vertices บน ไว้วาง accent


def neon_top_edge(d, top_verts, color):
    tN, tE, tS, tW = top_verts
    d.line([tW, tN], fill=color, width=1)
    d.line([tN, tE], fill=color, width=1)


def desk(accent=CYAN, ceo=False):
    img, d = _canvas(64, 64)
    cx, by = 32, 58
    top = box(d, cx, by, 56, 28, 12, PANEL_MID, PANEL_DARK, (10, 7, 22, 255))
    neon_top_edge(d, top, GOLD if ceo else BORDER_LIGHT)
    # จอมอนิเตอร์ (layer เดียวกัน — hologram_screen.gd จะ overlay แยกได้)
    box(d, cx, by - 12, 22, 11, 18, (8, 6, 16, 255), (6, 4, 12, 255), (5, 3, 10, 255))
    d.rectangle([cx - 9, by - 40, cx + 9, by - 30], fill=(6, 10, 20, 255), outline=accent)  # สกรีน
    d.line([cx - 7, by - 37, cx + 6, by - 37], fill=accent, width=1)
    d.line([cx - 7, by - 34, cx + 2, by - 34], fill=accent, width=1)
    return img


def chair(accent=CYAN):
    img, d = _canvas(32, 40)
    cx, by = 16, 36
    box(d, cx, by, 22, 11, 8, PANEL_MID, PANEL_DARK, (10, 7, 22, 255))   # เบาะ
    box(d, cx - 6, by - 8, 14, 7, 14, PANEL_MID, PANEL_DARK, (10, 7, 22, 255))  # พนัก
    d.line([cx - 10, by - 20, cx - 2, by - 24], fill=accent, width=1)
    return img


def table_meeting():
    img, d = _canvas(128, 80)
    top = box(d, 64, 74, 118, 56, 14, PANEL_MID, PANEL_DARK, (10, 7, 22, 255))
    neon_top_edge(d, top, PINK)
    return img


def whiteboard():
    img, d = _canvas(96, 64)
    cx, by = 48, 60
    # ขาตั้ง
    box(d, cx, by, 40, 14, 6, PANEL_DARK, (10, 7, 22, 255), (8, 6, 16, 255))
    # แผ่นกระดาน (frame ว่าง — เนื้อหา render runtime)
    d.rectangle([cx - 34, by - 52, cx + 34, by - 8], fill=(8, 10, 24, 230), outline=CYAN)
    d.rectangle([cx - 34, by - 52, cx + 34, by - 8], outline=CYAN)
    d.line([cx - 28, by - 44, cx + 10, by - 44], fill=(0, 229, 255, 120), width=1)
    d.line([cx - 28, by - 38, cx + 24, by - 38], fill=(0, 229, 255, 90), width=1)
    return img


def coffee_machine():
    img, d = _canvas(32, 48)
    cx, by = 16, 44
    box(d, cx, by, 22, 11, 30, PANEL_MID, PANEL_DARK, (10, 7, 22, 255))
    d.rectangle([cx - 5, by - 26, cx + 5, by - 20], fill=(6, 4, 12, 255), outline=ORANGE)  # จอ
    d.rectangle([cx - 4, by - 14, cx + 4, by - 10], fill=ORANGE)  # ถ้วย glow
    return img


def server_rack():
    img, d = _canvas(48, 96)
    cx, by = 24, 90
    box(d, cx, by, 34, 17, 70, PANEL_MID, PANEL_DARK, (10, 7, 22, 255))
    # LED แถว (layer กระพริบตาม LLM load — แยกสีม่วง/เขียว)
    for i in range(6):
        y = by - 64 + i * 10
        col = GREEN if i % 2 == 0 else PURPLE
        d.rectangle([cx - 10, y, cx - 6, y + 3], fill=col)
        d.rectangle([cx + 4, y, cx + 10, y + 2], fill=(col[0], col[1], col[2], 150))
    return img


def bunk_bed():
    img, d = _canvas(64, 80)
    cx, by = 32, 74
    box(d, cx, by, 56, 28, 16, PANEL_MID, PANEL_DARK, (10, 7, 22, 255))       # เตียงล่าง
    box(d, cx, by - 34, 56, 28, 16, PANEL_MID, PANEL_DARK, (10, 7, 22, 255))  # เตียงบน
    d.line([cx - 24, by - 30, cx - 24, by - 64], fill=BORDER_LIGHT, width=1)  # เสา
    d.rectangle([cx - 18, by - 18, cx + 2, by - 12], fill=(40, 64, 160, 180))  # หมอน blue
    return img


def plant(tall=False):
    h = 48 if tall else 40
    img, d = _canvas(32, 48)
    cx, by = 16, 44
    box(d, cx, by, 16, 8, 10, PANEL_MID, PANEL_DARK, (10, 7, 22, 255))  # กระถาง
    # ใบ
    cy = by - 10
    for r, col in ((10, (0, 110, 70, 255)), (7, (0, 160, 100, 255)), (4, GREEN)):
        d.ellipse([cx - r, cy - h // 2 - r, cx + r, cy - h // 2 + r], fill=col)
    return img


def main():
    desk(CYAN).save(OUT / "desk_agent.png")
    desk(GOLD, ceo=True).save(OUT / "desk_ceo.png")
    chair().save(OUT / "chair.png")
    table_meeting().save(OUT / "table_meeting.png")
    whiteboard().save(OUT / "board_whiteboard.png")
    coffee_machine().save(OUT / "machine_coffee.png")
    server_rack().save(OUT / "rack_server.png")
    bunk_bed().save(OUT / "bed_bunk.png")
    plant(False).save(OUT / "plant_a.png")
    plant(True).save(OUT / "plant_b.png")
    print(f"generated 10 furniture/props -> {OUT}")


if __name__ == "__main__":
    main()
