"""ป้าย neon "ET OFFICE" สำหรับ neon_signs.gd — เอียง isometric แนบผนัง N (ขวา)
(CEO ไกด์ มิ.ย.2026: ย้ายไปผนังขวา + วาดให้แนบระนาบกำแพง 2:1 ไม่ใช่ภาพแบนหันหน้าตรง)
ภาพแบน 160×48 → เฉือนแนวตั้ง slope 0.5 ขอบขวาลง → ออก 160×128 (ฐานเฉียงลงขวา)

รัน: ../.venv/Scripts/python.exe gen_placeholder_sign.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).parent.parent / "godot" / "assets" / "sprites" / "furniture"
OUT.mkdir(parents=True, exist_ok=True)

W, H = 160, 48
SLOPE = 0.5                   # dimetric 2:1 — เฉือนให้แนบผนัง N (ลาดลงขวา)
MAGENTA = (224, 64, 251)      # Neon Magenta จาก ART-SPEC — ป้าย ET OFFICE
PANEL = (14, 10, 30, 255)
BORDER = (42, 31, 78, 255)


def _flat() -> Image.Image:
    # วาดเล็กแล้วขยาย NEAREST ให้ได้ pixel ใหญ่แบบ retro
    small = Image.new("RGBA", (80, 24), (0, 0, 0, 0))
    d = ImageDraw.Draw(small)
    d.rounded_rectangle([0, 0, 79, 23], radius=3, fill=PANEL, outline=BORDER)
    d.rounded_rectangle([1, 1, 78, 22], radius=3, outline=(*MAGENTA, 140))
    d.text((9, 8), "ET OFFICE", fill=(*MAGENTA, 255))
    return small.resize((W, H), Image.NEAREST)


def make_sign() -> Image.Image:
    flat = _flat()
    extra = int(round(SLOPE * (W - 1)))
    # เฉือนแนวตั้ง: คอลัมน์ x เลื่อนลง slope*x (ขอบขวาต่ำกว่าขอบซ้าย → แนบผนัง N)
    return flat.transform((W, H + extra), Image.AFFINE,
                          (1, 0, 0, -SLOPE, 1, 0), resample=Image.NEAREST)


if __name__ == "__main__":
    make_sign().save(OUT / "sign_etoffice.png")
    print(f"saved {OUT / 'sign_etoffice.png'} (isometric, N wall)")
