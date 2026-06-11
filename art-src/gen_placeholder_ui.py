"""A-6 placeholder (บางส่วน) — speech bubble 9-patch สำหรับ hud.gd (M3-6)
ใช้ชั่วคราวจนกว่างานวาดจริงจะมาแทน (ชื่อไฟล์/ขนาดตรงสเปค — สลับไฟล์ได้เลย)
hologram screen frames (อีกครึ่งของ A-6) จะตามมากับ M3-7

รัน: ../.venv/Scripts/python.exe gen_placeholder_ui.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).parent.parent / "godot" / "assets" / "sprites" / "fx"
OUT.mkdir(parents=True, exist_ok=True)

# hologram cyan จาก ART-SPEC (LOCKED)
CYAN = (0, 229, 255)
SIZE = 24      # 9-patch base — margin 8px ทุกด้าน (ตั้งใน hud.gd)
RADIUS = 5


def make_bubble() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # พื้น hologram โปร่งแสงเข้ม + ขอบ cyan สว่าง 1px
    d.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=RADIUS,
                        fill=(0, 42, 56, 210), outline=(*CYAN, 255), width=1)
    # ขอบในจาง ๆ ให้ดูเป็นกระจก hologram
    d.rounded_rectangle([2, 2, SIZE - 3, SIZE - 3], radius=RADIUS - 2,
                        outline=(*CYAN, 60), width=1)
    return img


if __name__ == "__main__":
    make_bubble().save(OUT / "bubble_9patch.png")
    print(f"saved {OUT / 'bubble_9patch.png'}")
