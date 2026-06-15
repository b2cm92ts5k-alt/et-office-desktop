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


def vshear(img, slope=0.5, direction="right"):
    """เฉือนแนวตั้งให้ของแบน (ป้าย/whiteboard) ดูแนบระนาบกำแพง dimetric 2:1 (slope 0.5)
    direction='right' = ขอบขวาลง → แนบผนัง N (ลาดลงขวา)
    direction='left'  = ขอบซ้ายลง → แนบผนัง W (ลาดลงซ้าย)"""
    w, h = img.size
    extra = int(round(slope * (w - 1)))
    if direction == "right":
        coeffs = (1, 0, 0, -slope, 1, 0)               # คอลัมน์ x เลื่อนลง slope*x
    else:
        coeffs = (1, 0, 0, slope, 1, -slope * (w - 1))  # mirror — คอลัมน์ซ้ายลง
    return img.transform((w, h + extra), Image.AFFINE, coeffs, resample=Image.NEAREST)


def slab(d, ox, oy, lx, ly, h, top, left, right, edge=BORDER):
    """แท่ง dimetric ยาว lx×ly tile (1 tile = 64×32) สูง h — (ox,oy)=จอของมุม grid (0,0)
    คืน vertices หน้าบนไว้วาง accent (เหมือน box แต่ footprint เป็น parallelogram)"""
    def g(gx, gy):
        return (ox + (gx - gy) * 32, oy + (gx + gy) * 16)
    bN, bE, bS, bW = g(0, 0), g(lx, 0), g(lx, ly), g(0, ly)
    tN = (bN[0], bN[1] - h); tE = (bE[0], bE[1] - h)
    tS = (bS[0], bS[1] - h); tW = (bW[0], bW[1] - h)
    d.polygon([bW, bS, tS, tW], fill=left, outline=edge)   # หน้าซ้าย-หน้า
    d.polygon([bS, bE, tE, tS], fill=right, outline=edge)  # หน้าขวา-หน้า
    d.polygon([tN, tE, tS, tW], fill=top, outline=edge)    # หน้าบน
    return (tN, tE, tS, tW)


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
    """โต๊ะประชุมยาว 3 บล็อค (dimetric) — ยาวตามแกน +y (ลงซ้าย/ขึ้นขวา) ตามเส้นชมพูที่ CEO ไกด์
    (มิ.ย.2026 รอบ 2: รอบแรกวาดยาวแกน +x ลงขวา = กลับด้าน → แก้เป็น lx=1,ly=3)"""
    img, d = _canvas(144, 96)
    # footprint (0,0)-(1,3): ยาวแกน +y → ox=104,oy=23 ให้กึ่งกลาง canvas
    top = slab(d, 104, 23, 1, 3, 14, PANEL_MID, PANEL_DARK, (10, 7, 22, 255))
    neon_top_edge(d, top, PINK)
    # เส้น hologram กลางโต๊ะ ตามแนวยาว (กลางปลายสั้นทั้งสองด้าน)
    tN, tE, tS, tW = top
    m0 = ((tN[0] + tE[0]) / 2, (tN[1] + tE[1]) / 2)
    m1 = ((tW[0] + tS[0]) / 2, (tW[1] + tS[1]) / 2)
    d.line([m0, m1], fill=PINK[:3] + (90,), width=1)
    return img


def whiteboard():
    """Whiteboard hologram แนบผนัง W (เอียง isometric) — frame ว่าง เนื้อหา render runtime
    (CEO ไกด์ มิ.ย.2026: วาดใหม่ให้แนบกำแพงในกรอบฟ้า ไม่ใช่ตั้งพื้น)"""
    bw, bh = 96, 60
    flat = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    fd = ImageDraw.Draw(flat)
    fd.rectangle([0, 0, bw - 1, bh - 1], fill=(8, 10, 24, 230), outline=CYAN)
    fd.rectangle([3, 3, bw - 4, bh - 4], outline=(0, 229, 255, 90))
    for i, (x2, a) in enumerate(((58, 130), (78, 100), (48, 80))):
        y = 14 + i * 12
        fd.line([10, y, x2, y], fill=(0, 229, 255, a), width=2)
    # มุมยึดผนัง (corner bracket)
    for cx, cy, dx in ((2, 2, 1), (bw - 3, 2, -1)):
        fd.line([(cx, cy), (cx + dx * 5, cy)], fill=CYAN, width=1)
    return vshear(flat, 0.5, "left")


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


def _sofa_cushions(d, top, n):
    """วางเบาะ ORANGE บนหน้าบนของโซฟา (top = vertices หน้าบน) แบ่ง n ที่นั่ง"""
    tN, tE, tS, tW = top
    for k in range(n):
        a, b = k / n, (k + 1) / n
        p1 = (tW[0] + (tS[0] - tW[0]) * a, tW[1] + (tS[1] - tW[1]) * a)
        p2 = (tW[0] + (tS[0] - tW[0]) * b, tW[1] + (tS[1] - tW[1]) * b)
        p3 = (tN[0] + (tE[0] - tN[0]) * b, tN[1] + (tE[1] - tN[1]) * b)
        p4 = (tN[0] + (tE[0] - tN[0]) * a, tN[1] + (tE[1] - tN[1]) * a)
        d.polygon([p1, p2, p3, p4], outline=ORANGE[:3] + (220,))


def sofa_small():
    """โซฟาเล็ก 1 บล็อค — ที่นั่ง + พนักพิง (Cafe)"""
    img, d = _canvas(72, 56)
    ox, oy = 36, 16
    seat = slab(d, ox, oy, 1, 1, 10, PANEL_MID, PANEL_DARK, (10, 7, 22, 255))
    _sofa_cushions(d, seat, 1)
    # พนักพิงด้านหลัง (แนว grid x, ชิดขอบ N→E) เตี้ย ๆ
    slab(d, ox, oy - 10, 1, 0, 14, PANEL_MID, PANEL_DARK, (10, 7, 22, 255))
    return img


def sofa_long():
    """โซฟายาว 3 บล็อค — ที่นั่งยาว + พนักพิงยาว (Cafe)"""
    img, d = _canvas(144, 96)
    ox, oy = 38, 26
    seat = slab(d, ox, oy, 3, 1, 10, PANEL_MID, PANEL_DARK, (10, 7, 22, 255))
    _sofa_cushions(d, seat, 3)
    slab(d, ox, oy - 10, 3, 0, 14, PANEL_MID, PANEL_DARK, (10, 7, 22, 255))  # พนักพิงยาว
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
    sofa_small().save(OUT / "sofa_small.png")
    sofa_long().save(OUT / "sofa_long.png")
    print(f"generated 12 furniture/props -> {OUT}")


if __name__ == "__main__":
    main()
