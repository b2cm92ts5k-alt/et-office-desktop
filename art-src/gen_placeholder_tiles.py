"""A-2 placeholder tiles — generate dimetric tiles ตาม docs/ART-SPEC.md
ใช้ชั่วคราวจนกว่างานวาดจริงจะมาแทน (ชื่อไฟล์/ขนาดตรงสเปคเป๊ะ — สลับไฟล์ได้เลย)

รัน: ../.venv/Scripts/python.exe gen_placeholder_tiles.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).parent.parent / "godot" / "assets" / "sprites" / "furniture"
OUT.mkdir(parents=True, exist_ok=True)

# palette จาก ART-SPEC (LOCKED)
BG_DEEP = (7, 5, 15, 255)        # 07050F
PANEL_DARK = (14, 10, 30, 255)   # 0E0A1E
PANEL_MID = (20, 15, 40, 255)    # 140F28
BORDER = (42, 31, 78, 255)       # 2A1F4E
BORDER_LIGHT = (74, 48, 128, 255)  # 4A3080

TILE_W, TILE_H = 64, 32
WALL_H = 96


def diamond(w: int, h: int) -> list[tuple[int, int]]:
    return [(w // 2, 0), (w - 1, h // 2), (w // 2, h - 1), (0, h // 2)]


def make_floor(fill, edge, highlight=None) -> Image.Image:
    img = Image.new("RGBA", (TILE_W, TILE_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon(diamond(TILE_W, TILE_H), fill=fill, outline=edge)
    if highlight:  # เส้น highlight ขอบบนซ้าย — แสงสะท้อนจาง ๆ (reflective hint)
        d.line([(TILE_W // 2, 1), (1, TILE_H // 2)], fill=highlight, width=1)
    return img


def make_wall(facing: str) -> Image.Image:
    """ผนัง dimetric สูง 96px — facing 'n' (ขวาบน) หรือ 'w' (ซ้ายบน)"""
    img = Image.new("RGBA", (TILE_W, WALL_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    half_w, half_h = TILE_W // 2, TILE_H // 2
    top = WALL_H - TILE_H  # 64 — ความสูงผนังเหนือ tile
    if facing == "w":  # ระนาบซ้าย: จาก (0,half) ขึ้นไป
        pts = [(0, half_h + top), (half_w, TILE_H - 1 + top),
               (half_w, TILE_H - 1), (0, half_h)]
    else:  # ระนาบขวา
        pts = [(half_w, TILE_H - 1 + top), (TILE_W - 1, half_h + top),
               (TILE_W - 1, half_h), (half_w, TILE_H - 1)]
    d.polygon(pts, fill=PANEL_MID, outline=BORDER)
    # เส้นขอบบนรับแสง
    d.line([pts[3], pts[2]], fill=BORDER_LIGHT, width=1)
    return img


def main() -> None:
    make_floor(PANEL_DARK, BORDER).save(OUT / "tile_floor_a.png")
    make_floor(PANEL_MID, BORDER, BORDER_LIGHT).save(OUT / "tile_floor_b.png")
    make_wall("n").save(OUT / "wall_n.png")
    make_wall("w").save(OUT / "wall_w.png")
    print(f"generated 4 tiles -> {OUT}")


if __name__ == "__main__":
    main()
