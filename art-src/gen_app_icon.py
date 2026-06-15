"""A-8 — app icon (.ico) + system tray icon (tray.png) โทน ET Office cyberpunk

โลโก้ "ET" นีออน บนพื้นเข้ม กรอบ magenta — palette LOCKED (ART-SPEC §2) ตรงกับ
ไอคอน fallback ที่ host.py วาดด้วยมือ (sidebar/host.py Tray._draw_icon)

ออก 2 ไฟล์:
  art-src/icon.ico            → ฝัง EXE ทั้ง 3 ตัว (installer/et-office.spec)
  sidebar/assets/tray.png     → host.py โหลดแทน fallback ถ้าไฟล์นี้มี

วาดที่ความละเอียดสูง (256) เส้นหนาให้รอด downscale ไป 16px แล้วยังอ่าน "ET" ออก
รัน:  ../.venv/Scripts/python.exe gen_app_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).parent.parent
ICO_OUT = Path(__file__).parent / "icon.ico"
TRAY_OUT = ROOT / "sidebar" / "assets" / "tray.png"

# palette (LOCKED — ART-SPEC §2)
BG = (7, 5, 15, 255)
PANEL = (14, 10, 30, 255)
MAGENTA = (224, 64, 251, 255)
CYAN = (0, 229, 255, 255)
GOLD = (255, 224, 64, 255)

ICO_SIZES = [256, 128, 64, 48, 32, 24, 16]


def _logo(size: int) -> Image.Image:
    """โลโก้ ET เต็ม canvas — สเกลตาม size ให้คมทุกความละเอียด"""
    s = size
    u = s / 64.0  # 1 หน่วย = 1px ตอน 64 (เทียบ fallback เดิม) → scale ขึ้น
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def R(x0, y0, x1, y1, fill, outline=None, w=1):
        d.rounded_rectangle([x0 * u, y0 * u, x1 * u, y1 * u],
                            radius=max(1, int(3 * u)), fill=fill,
                            outline=outline, width=max(1, int(w * u)))

    # พื้น + กรอบนีออน
    R(2, 2, 62, 62, PANEL, outline=MAGENTA, w=3)
    R(5, 5, 59, 59, BG)

    stroke = max(2, int(6 * u))
    # ตัว E (cyan) — ซ้าย
    ex0 = 14 * u
    d.line([(ex0, 18 * u), (ex0, 46 * u)], fill=CYAN, width=stroke)            # แกนตั้ง
    d.line([(ex0, 18 * u), (30 * u, 18 * u)], fill=CYAN, width=stroke)         # บน
    d.line([(ex0, 32 * u), (27 * u, 32 * u)], fill=CYAN, width=stroke)         # กลาง
    d.line([(ex0, 46 * u), (30 * u, 46 * u)], fill=CYAN, width=stroke)         # ล่าง
    # ตัว T (magenta) — ขวา
    d.line([(36 * u, 18 * u), (52 * u, 18 * u)], fill=MAGENTA, width=stroke)   # บน
    d.line([(44 * u, 18 * u), (44 * u, 46 * u)], fill=MAGENTA, width=stroke)   # แกนตั้ง
    # จุด accent ทอง (มุมขวาล่าง = สถานะ "live")
    d.ellipse([48 * u, 44 * u, 54 * u, 50 * u], fill=GOLD)

    # เรืองแสงนีออนนิด ๆ (เฉพาะ size ใหญ่ — เล็กไป blur แล้วเละ)
    if s >= 48:
        glow = img.filter(ImageFilter.GaussianBlur(radius=max(1, int(1.5 * u))))
        out = Image.alpha_composite(glow, img)
        return out
    return img


def main() -> None:
    TRAY_OUT.parent.mkdir(parents=True, exist_ok=True)

    # tray.png — host.py resize เป็น 64 อยู่แล้ว แต่ให้ไฟล์ 128 ไว้คมกว่า
    tray = _logo(128)
    tray.save(TRAY_OUT)
    print(f"tray  -> {TRAY_OUT}")

    # icon.ico — หลายขนาดในไฟล์เดียว (Windows เลือกใช้ตามจุดที่แสดง)
    base = _logo(256)
    base.save(ICO_OUT, format="ICO",
              sizes=[(n, n) for n in ICO_SIZES])
    print(f"icon  -> {ICO_OUT}  ({', '.join(str(n) for n in ICO_SIZES)})")


if __name__ == "__main__":
    main()
