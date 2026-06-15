"""A-6 (ครึ่งหลัง) — hologram screen frames สำหรับ hologram_screen.gd (M3-7)
speech bubble 9-patch ทำแล้วใน gen_placeholder_ui.py — ไฟล์นี้เติม "จอ hologram"

ออก 2 ไฟล์ใน godot/assets/sprites/fx/ :
  holo_frame_9patch.png  24×24  — กรอบจอ hologram (9-patch, margin 6) ยืดเป็นจอ
                                   desk 64×64 / whiteboard 96×64 / panel ใด ๆ ได้
  holo_scanline.png      32×32  — แผ่น scanline โปร่ง วางทับเนื้อจอให้ดูเป็น hologram

palette LOCKED (ART-SPEC §2: hologram = cyan). drop-in swap ชื่อ/ขนาดเดิม
รัน: ../.venv/Scripts/python.exe gen_holo_frames.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).parent.parent / "godot" / "assets" / "sprites" / "fx"
OUT.mkdir(parents=True, exist_ok=True)

CYAN = (0, 229, 255)


def make_frame() -> Image.Image:
    """9-patch: มุมคงรูป ขอบ/กลางยืดได้ — margin 6px (ตั้งใน hologram_screen.gd)"""
    s = 24
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # พื้นจอโปร่งแสงเข้ม (กระจก hologram)
    d.rectangle([1, 1, s - 2, s - 2], fill=(0, 38, 52, 150))
    # ขอบนอก cyan สว่าง + ขอบในจาง
    d.rectangle([0, 0, s - 1, s - 1], outline=(*CYAN, 255), width=1)
    d.rectangle([3, 3, s - 4, s - 4], outline=(*CYAN, 70), width=1)
    # มุมไฮไลต์ (corner bracket) ให้รู้ว่าเป็นจอ — อยู่ในโซนมุม 6px คงรูป
    for cx, cy, dx, dy in ((1, 1, 1, 1), (s - 2, 1, -1, 1),
                           (1, s - 2, 1, -1), (s - 2, s - 2, -1, -1)):
        d.line([(cx, cy), (cx + dx * 3, cy)], fill=(*CYAN, 255), width=1)
        d.line([(cx, cy), (cx, cy + dy * 3)], fill=(*CYAN, 255), width=1)
    return img


def make_scanline() -> Image.Image:
    """แผ่น scanline โปร่ง — tile/ยืดทับเนื้อจอ ให้ดูเป็นภาพฉาย hologram"""
    s = 32
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for y in range(0, s, 2):
        d.line([(0, y), (s - 1, y)], fill=(*CYAN, 30), width=1)
    return img


def main() -> None:
    make_frame().save(OUT / "holo_frame_9patch.png")
    make_scanline().save(OUT / "holo_scanline.png")
    print("saved holo_frame_9patch.png (24x24, 9-patch margin 6)")
    print("saved holo_scanline.png (32x32, overlay)")


if __name__ == "__main__":
    main()
