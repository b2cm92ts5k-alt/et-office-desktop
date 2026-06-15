"""A-6 (เพิ่ม) / M3-7 — hologram screen CONTENT sheet สำหรับ hologram_screen.gd
holo_frame_9patch + holo_scanline ทำแล้วใน gen_holo_frames.py — ไฟล์นี้เติม "เนื้อจอ"
ที่สลับอนิเมชันตาม state ของ agent

ออก holo_content.png ใน godot/assets/sprites/fx/ :
  ขนาด 96×80 = 4 cols (frame) × 5 rows (state), ช่องละ 24×16
  row 0 STANDBY  (idle — เส้น baseline + จุดวิ่ง)
  row 1 WORKING  (โค้ดเลื่อนขึ้น)
  row 2 THINKING (จุด 3 จุดไล่กระพริบ)
  row 3 DONE     (เครื่องหมายถูกเด้ง) — ใช้ตอน flash
  row 4 ERROR    (กากบาท + glitch)   — ใช้ตอน flash

palette LOCKED (ART-SPEC §2: hologram = cyan). drop-in swap ชื่อ/ขนาดเดิม
รัน: ../.venv/Scripts/python.exe gen_holo_content.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).parent.parent / "godot" / "assets" / "sprites" / "fx"
OUT.mkdir(parents=True, exist_ok=True)

CW, CH = 24, 16     # cell (content) size
COLS, ROWS = 4, 5
CYAN = (0, 229, 255)
GREEN = (0, 255, 159)
RED = (255, 64, 96)


def _a(color, a: float) -> tuple:
    return (color[0], color[1], color[2], max(0, min(255, int(a))))


def standby(d: ImageDraw.ImageDraw, ox: int, oy: int, f: int) -> None:
    """จอพัก: เส้น baseline จาง + จุดสว่างวิ่งซ้าย→ขวา"""
    y = oy + CH // 2
    d.line([(ox + 3, y), (ox + CW - 4, y)], fill=_a(CYAN, 70), width=1)
    px = ox + 4 + f * 4
    d.ellipse([px - 1, y - 1, px + 1, y + 1], fill=_a(CYAN, 220))


def working(d: ImageDraw.ImageDraw, ox: int, oy: int, f: int) -> None:
    """โค้ดรัน: 4 บรรทัดยาวต่างกัน เลื่อนขึ้นทีละเฟรม"""
    widths = [14, 9, 17, 11, 7, 15]
    for row in range(4):
        idx = (row + f) % len(widths)
        w = widths[idx]
        yy = oy + 2 + row * 3
        bright = 230 if row == 0 else 150
        d.line([(ox + 3, yy), (ox + 3 + w, yy)], fill=_a(CYAN, bright), width=1)


def thinking(d: ImageDraw.ImageDraw, ox: int, oy: int, f: int) -> None:
    """คิด: จุด 3 จุด ไล่สว่างทีละจุด"""
    y = oy + CH // 2
    for i in range(3):
        cx = ox + 7 + i * 5
        on = (f % 4) == i
        d.ellipse([cx - 1, y - 1, cx + 1, y + 1], fill=_a(CYAN, 235 if on else 80))


def done(d: ImageDraw.ImageDraw, ox: int, oy: int, f: int) -> None:
    """เสร็จ: เครื่องหมายถูกวาดเข้า (เขียว)"""
    cx, cy = ox + CW // 2, oy + CH // 2
    grow = (f + 1) / COLS
    p0, p1, p2 = (cx - 5, cy), (cx - 1, cy + 4), (cx + 6, cy - 5)
    d.line([p0, p1], fill=_a(GREEN, 255), width=2)
    if grow > 0.4:
        g = (grow - 0.4) / 0.6
        ex = p1[0] + (p2[0] - p1[0]) * g
        ey = p1[1] + (p2[1] - p1[1]) * g
        d.line([p1, (ex, ey)], fill=_a(GREEN, 255), width=2)


def error(d: ImageDraw.ImageDraw, ox: int, oy: int, f: int) -> None:
    """ผิดพลาด: กากบาทแดง + glitch สั่นแนวนอน"""
    cx, cy = ox + CW // 2, oy + CH // 2
    jit = (f % 2) * 2 - 1
    d.line([(cx - 5 + jit, cy - 5), (cx + 5 + jit, cy + 5)], fill=_a(RED, 255), width=2)
    d.line([(cx + 5 + jit, cy - 5), (cx - 5 + jit, cy + 5)], fill=_a(RED, 255), width=2)
    if f % 2 == 0:  # เส้น glitch
        gy = oy + 3 + f
        d.line([(ox + 1, gy), (ox + CW - 2, gy)], fill=_a(RED, 90), width=1)


ROWS_FN = [standby, working, thinking, done, error]


def main() -> None:
    img = Image.new("RGBA", (CW * COLS, CH * ROWS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for row, fn in enumerate(ROWS_FN):
        for col in range(COLS):
            fn(d, col * CW, row * CH, col)
    img.save(OUT / "holo_content.png")
    print(f"saved holo_content.png ({img.width}x{img.height}, {COLS} frames x {ROWS} states)")


if __name__ == "__main__":
    main()
