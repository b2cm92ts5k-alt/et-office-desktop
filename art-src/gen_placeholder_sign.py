"""A-7 placeholder (บางส่วน) — ป้าย neon "ET OFFICE" 160x48 สำหรับ neon_signs.gd (M2-12)
ใช้ชั่วคราวจนกว่างานวาดจริงจะมาแทน (ชื่อไฟล์/ขนาดตรง ART-SPEC §4 — สลับไฟล์ได้เลย)

รัน: ../.venv/Scripts/python.exe gen_placeholder_sign.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).parent.parent / "godot" / "assets" / "sprites" / "furniture"
OUT.mkdir(parents=True, exist_ok=True)

W, H = 160, 48
MAGENTA = (224, 64, 251)      # Neon Magenta จาก ART-SPEC — ป้าย ET OFFICE
PANEL = (14, 10, 30, 255)
BORDER = (42, 31, 78, 255)


def make_sign() -> Image.Image:
    # วาดเล็กแล้วขยาย NEAREST ให้ได้ pixel ใหญ่แบบ retro
    small = Image.new("RGBA", (80, 24), (0, 0, 0, 0))
    d = ImageDraw.Draw(small)
    d.rounded_rectangle([0, 0, 79, 23], radius=3, fill=PANEL, outline=BORDER)
    d.rounded_rectangle([1, 1, 78, 22], radius=3, outline=(*MAGENTA, 140))
    # ตัวอักษรใช้ font bitmap default ของ PIL (ตัวเล็ก คม เหมาะ pixel art)
    d.text((9, 8), "ET OFFICE", fill=(*MAGENTA, 255))
    return small.resize((W, H), Image.NEAREST)


if __name__ == "__main__":
    make_sign().save(OUT / "sign_etoffice.png")
    print(f"saved {OUT / 'sign_etoffice.png'}")
