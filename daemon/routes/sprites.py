"""/sprites — custom agent spritesheet (M6-2 v2)

CEO feedback: hire dialog ให้อัพโหลด spritesheet ของตัวเองได้ตาม template
spec จาก docs/ART-SPEC.md §3: PNG 192x192 = 6 เฟรม (คอลัมน์) x 4 ทิศ (แถว SE,SW,NE,NW)
ไฟล์เก็บใน daemon/data/sprites/ (นอก git) — Godot โหลดผ่าน GET /sprites/files/<name>
"""
from __future__ import annotations

import io
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image, ImageDraw

router = APIRouter(tags=["sprites"])

SPRITES_DIR = Path(__file__).parent.parent / "data" / "sprites"
SPRITES_DIR.mkdir(parents=True, exist_ok=True)

SHEET_SIZE = (192, 192)   # ART-SPEC: 6 cols x 32px, 4 rows x 48px
CELL_W, CELL_H = 32, 48
ROW_LABELS = ["SE", "SW", "NE", "NW"]
MAX_BYTES = 1024 * 1024   # 1MB เกินพอสำหรับ pixel art 192x192


@router.post("/sprites/upload")
async def upload_sprite(file: UploadFile) -> dict:
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(400, "ไฟล์ใหญ่เกิน 1MB")
    try:
        img = Image.open(io.BytesIO(data))
        fmt, size = img.format, img.size
    except Exception:
        raise HTTPException(400, "อ่านไฟล์รูปไม่ได้ — ต้องเป็น PNG")
    if fmt != "PNG":
        raise HTTPException(400, "ต้องเป็น PNG เท่านั้น (ตาม ART-SPEC)")
    if size != SHEET_SIZE:
        raise HTTPException(400,
            f"ขนาดต้องเป็น {SHEET_SIZE[0]}x{SHEET_SIZE[1]}px (ได้ {size[0]}x{size[1]}) "
            "— โหลด template จากปุ่มในหน้า hire ได้")
    name = f"{uuid4().hex[:12]}.png"
    (SPRITES_DIR / name).write_bytes(data)
    return {"file": name, "url": f"/sprites/files/{name}"}


@router.get("/sprites/template")
def sprite_template() -> Response:
    """template PNG โปร่งใส + เส้น grid 6x4 + ป้ายทิศต่อแถว — วาดทับแล้วอัพกลับได้เลย"""
    img = Image.new("RGBA", SHEET_SIZE, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for row in range(4):
        for col in range(6):
            x0, y0 = col * CELL_W, row * CELL_H
            if (row + col) % 2 == 0:  # ช่องสลับโทนให้เห็นขอบเฟรมชัด
                d.rectangle([x0, y0, x0 + CELL_W - 1, y0 + CELL_H - 1], fill=(42, 31, 78, 60))
            d.rectangle([x0, y0, x0 + CELL_W - 1, y0 + CELL_H - 1], outline=(74, 48, 128, 180))
    for row, label in enumerate(ROW_LABELS):
        d.text((2, row * CELL_H + 1), label, fill=(0, 229, 255, 220))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(content=buf.getvalue(), media_type="image/png",
                    headers={"Content-Disposition": 'attachment; filename="char_template.png"'})
