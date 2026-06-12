"""/sprites — custom agent spritesheet (M6-2 v2)

CEO feedback: hire dialog ให้อัพโหลด spritesheet ของตัวเองได้ตาม template
layout v2 (CEO อนุมัติ มิ.ย. 2026) — ช่องละ 32x48, 6 คอลัมน์:
  แถว 1-4  WALK  SE/SW/NE/NW  6 เฟรม   |  แถว 5-8  IDLE SE/SW/NE/NW  4 เฟรม
  แถว 9-10 SIT+TYPE SE/SW     4 เฟรม   |  แถว 11   SLEEP             2 เฟรม
รับ 2 ขนาด: 192x192 (เดินอย่างเดียว — layout เดิม) / 192x528 (ครบทุกท่า)
หมายเหตุ: engine เล่นเฉพาะแถวเดินไปก่อน (อนิเมชัน idle/sit/sleep = งานรอบหน้า)
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

CELL_W, CELL_H = 32, 48
SHEET_W = CELL_W * 6
WALK_SIZE = (SHEET_W, CELL_H * 4)    # 192x192 — แผ่นเดินอย่างเดียว (back-compat)
FULL_SIZE = (SHEET_W, CELL_H * 11)   # 192x528 — ครบทุกท่า (template v2)
MAX_BYTES = 1024 * 1024

# (label, จำนวนเฟรมที่ใช้) ต่อแถว — ตาม layout v2
ROWS = [
    ("WALK SE", 6), ("WALK SW", 6), ("WALK NE", 6), ("WALK NW", 6),
    ("IDLE SE", 4), ("IDLE SW", 4), ("IDLE NE", 4), ("IDLE NW", 4),
    ("SIT SE", 4), ("SIT SW", 4),
    ("SLEEP", 2),
]


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
    if size not in (WALK_SIZE, FULL_SIZE):
        raise HTTPException(400,
            f"ขนาดต้องเป็น 192x192 (เดินอย่างเดียว) หรือ 192x528 (ครบทุกท่า) "
            f"— ได้ {size[0]}x{size[1]} — โหลด template จากปุ่มในหน้า hire ได้")
    name = f"{uuid4().hex[:12]}.png"
    (SPRITES_DIR / name).write_bytes(data)
    return {"file": name, "url": f"/sprites/files/{name}"}


@router.get("/sprites/template")
def sprite_template() -> Response:
    """template v2 (192x528) — grid + ป้ายท่า/ทิศต่อแถว, ช่องที่ไม่ใช้ถมเข้มไว้
    วิธีใช้: เปิดใน Aseprite วาดบน layer ใหม่ → ซ่อน/ลบ layer template ก่อน export"""
    img = Image.new("RGBA", FULL_SIZE, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for row, (label, used) in enumerate(ROWS):
        for col in range(6):
            x0, y0 = col * CELL_W, row * CELL_H
            box = [x0, y0, x0 + CELL_W - 1, y0 + CELL_H - 1]
            if col >= used:                    # ช่องเกินจำนวนเฟรม — ปล่อยว่าง/โปร่งใส
                d.rectangle(box, fill=(10, 8, 20, 120))
                d.line([x0, y0, x0 + CELL_W - 1, y0 + CELL_H - 1], fill=(74, 48, 128, 120))
            elif (row + col) % 2 == 0:         # ช่องวาด — สลับโทนให้เห็นขอบเฟรม
                d.rectangle(box, fill=(42, 31, 78, 60))
            d.rectangle(box, outline=(74, 48, 128, 180))
        d.text((2, row * CELL_H + 1), label, fill=(0, 229, 255, 220))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(content=buf.getvalue(), media_type="image/png",
                    headers={"Content-Disposition": 'attachment; filename="char_template.png"'})
