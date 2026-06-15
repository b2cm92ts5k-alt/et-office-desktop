"""A-5 — FX flipbooks ตาม ART-SPEC §5: 32×32 px, 8 frames @ 12 fps, RGBA โปร่งใส
sheet แนวนอน 8 ช่อง (256×32) — คอลัมน์ = frame (convention เดียวกับ char sheet)

  fx_done ✅ · fx_error ❌ · fx_proposal 💡 · fx_working ⚡ · fx_zzz 💤

palette LOCKED (ART-SPEC §2). drop-in swap: วาดเองทับชื่อ/ขนาดเดิมได้ 1:1
รัน: ../.venv/Scripts/python.exe gen_fx.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).parent.parent / "godot" / "assets" / "sprites" / "fx"
OUT.mkdir(parents=True, exist_ok=True)

F = 32        # frame size
N = 8         # frames
CX = CY = 16  # frame center

# palette (LOCKED — ART-SPEC §2)
GREEN = (0, 255, 159)
RED = (255, 64, 96)
GOLD = (255, 224, 64)
CYAN = (0, 229, 255)
BLUE = (96, 160, 255)
WHITE = (235, 240, 255)


def _sheet() -> tuple[Image.Image, list]:
    img = Image.new("RGBA", (F * N, F), (0, 0, 0, 0))
    cells = []
    for i in range(N):
        c = Image.new("RGBA", (F, F), (0, 0, 0, 0))
        cells.append(c)
    return img, cells


def _paste(img: Image.Image, cells: list) -> Image.Image:
    for i, c in enumerate(cells):
        img.alpha_composite(c, (i * F, 0))
    return img


def _a(color, a: float) -> tuple:
    return (color[0], color[1], color[2], max(0, min(255, int(a))))


def ease_out(t: float) -> float:
    return 1.0 - (1.0 - t) ** 2


def fx_done() -> Image.Image:
    """เครื่องหมายถูกเด้งขึ้น + วงแหวนขยายจางหาย"""
    img, cells = _sheet()
    for i in range(N):
        d = ImageDraw.Draw(cells[i])
        t = i / (N - 1)
        grow = ease_out(min(1.0, t * 1.8))           # check วาดเข้าเร็วช่วงต้น
        # วงแหวนขยาย
        if t > 0.15:
            r = 4 + (t - 0.15) * 26
            d.ellipse([CX - r, CY - r, CX + r, CY + r],
                      outline=_a(GREEN, 200 * (1 - t)), width=2)
        # check mark (สองเส้น) วาดตามสัดส่วน grow
        p0, p1, p2 = (10, 17), (14, 22), (23, 10)
        midx = p0[0] + (p1[0] - p0[0]) * min(1.0, grow * 2)
        midy = p0[1] + (p1[1] - p0[1]) * min(1.0, grow * 2)
        d.line([p0, (midx, midy)], fill=_a(GREEN, 255), width=3)
        if grow > 0.5:
            g2 = (grow - 0.5) * 2
            ex = p1[0] + (p2[0] - p1[0]) * g2
            ey = p1[1] + (p2[1] - p1[1]) * g2
            d.line([p1, (ex, ey)], fill=_a(GREEN, 255), width=3)
    return _paste(img, cells)


def fx_error() -> Image.Image:
    """กากบาทแดงสั่น + แฟลชวาบ"""
    img, cells = _sheet()
    for i in range(N):
        d = ImageDraw.Draw(cells[i])
        t = i / (N - 1)
        shake = int(round(math.sin(t * math.pi * 4) * 2 * (1 - t)))
        a = 255 if i < 5 else int(255 * (1 - (i - 4) / 4))   # ค้างแล้วจางท้าย
        ox = shake
        d.line([(10 + ox, 10), (22 + ox, 22)], fill=_a(RED, a), width=3)
        d.line([(22 + ox, 10), (10 + ox, 22)], fill=_a(RED, a), width=3)
        if i < 2:  # แฟลชวงกลม 2 เฟรมแรก
            d.ellipse([4, 4, 28, 28], outline=_a(RED, 120), width=2)
    return _paste(img, cells)


def fx_proposal() -> Image.Image:
    """หลอดไฟ 💡 เรืองสว่างเป็นจังหวะ + รัศมีกระพริบ"""
    img, cells = _sheet()
    for i in range(N):
        d = ImageDraw.Draw(cells[i])
        t = i / (N - 1)
        pulse = (math.sin(t * math.pi * 2) + 1) / 2     # 0..1
        # รัศมีแฉก
        for ang in range(0, 360, 45):
            rad = math.radians(ang)
            r1, r2 = 11, 11 + 4 * pulse
            d.line([(CX + math.cos(rad) * r1, CY - 3 + math.sin(rad) * r1),
                    (CX + math.cos(rad) * r2, CY - 3 + math.sin(rad) * r2)],
                   fill=_a(GOLD, 120 + 100 * pulse), width=1)
        # หลอดไฟ (วงกลม) + ขั้ว
        glow = 160 + 95 * pulse
        d.ellipse([10, 6, 22, 18], fill=_a(GOLD, glow), outline=_a(WHITE, 220), width=1)
        d.rectangle([13, 18, 19, 22], fill=_a((180, 150, 40), 255))   # ขั้วหลอด
        d.line([(13, 24), (19, 24)], fill=_a((120, 100, 30), 255), width=1)
    return _paste(img, cells)


def fx_working() -> Image.Image:
    """สายฟ้า ⚡ กระพริบ + จิตเตอร์เล็กน้อย"""
    img, cells = _sheet()
    bolt = [(18, 4), (11, 17), (16, 17), (13, 28), (22, 13), (16, 13)]
    for i in range(N):
        d = ImageDraw.Draw(cells[i])
        t = i / (N - 1)
        on = 255 if (i % 2 == 0) else 150            # กระพริบสลับเฟรม
        jit = 1 if (i % 2) else 0
        pts = [(x + jit, y) for (x, y) in bolt]
        d.polygon(pts, fill=_a(CYAN, on), outline=_a(WHITE, on))
        if i % 2 == 0:  # ประกายตอนสว่าง
            d.ellipse([CX - 13, CY - 13, CX + 13, CY + 13], outline=_a(CYAN, 70), width=1)
    return _paste(img, cells)


def fx_zzz() -> Image.Image:
    """ตัว Z ลอยขึ้นไล่ขนาด แล้วจางหาย (สถานะ sleep)"""
    img, cells = _sheet()

    def draw_z(d: ImageDraw.ImageDraw, cx: float, cy: float, s: float, a: float) -> None:
        x0, x1 = cx - s, cx + s
        y0, y1 = cy - s, cy + s
        d.line([(x0, y0), (x1, y0)], fill=_a(BLUE, a), width=2)   # บน
        d.line([(x1, y0), (x0, y1)], fill=_a(BLUE, a), width=2)   # ทแยง
        d.line([(x0, y1), (x1, y1)], fill=_a(BLUE, a), width=2)   # ล่าง

    for i in range(N):
        d = ImageDraw.Draw(cells[i])
        t = i / (N - 1)
        # สาม Z ไล่เฟส ลอยขึ้น+โต+จาง
        for k in range(3):
            ph = (t + k / 3.0) % 1.0
            cy = 24 - ph * 18
            cx = 13 + k * 3 + ph * 4
            s = 2.5 + ph * 2.5
            a = 255 * (1 - ph)
            draw_z(d, cx, cy, s, a)
    return _paste(img, cells)


def main() -> None:
    fx = {
        "fx_done.png": fx_done(),
        "fx_error.png": fx_error(),
        "fx_proposal.png": fx_proposal(),
        "fx_working.png": fx_working(),
        "fx_zzz.png": fx_zzz(),
    }
    for name, sheet in fx.items():
        sheet.save(OUT / name)
        print(f"saved {name}  ({sheet.width}x{sheet.height}, {N} frames)")


if __name__ == "__main__":
    main()
