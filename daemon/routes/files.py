"""File drop (M9-2) — รับไฟล์ที่ผู้ใช้ลากใส่ terminal → เก็บใน <workspace>/_inbox/

แนวทาง: อ่านเนื้อหาไฟล์ฝั่ง client (FileReader) แล้วอัปโหลดเข้ามา — ไม่ต้องพึ่ง
OS path / pywebview js_api bridge (ที่ WebView2 เครื่องนี้มีปัญหา). ไฟล์ลงใต้ workspace
→ agent อ่านต่อผ่าน ToolExecutor (read_file "_inbox/<name>") ได้ทันที
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..services.tool_executor import WorkspaceError, _resolve, workspace_root

router = APIRouter(tags=["files"])

INBOX = "_inbox"
MAX_BYTES = 20_000_000  # 20MB ต่อไฟล์
_UNSAFE = re.compile(r"[^0-9A-Za-z฀-๿._-]+")  # เก็บอังกฤษ/ไทย/ตัวเลข/._- ที่เหลือเป็น _


@router.post("/files/drop")
async def drop_file(file: UploadFile = File(...)) -> dict:
    try:
        root = workspace_root()
    except WorkspaceError as e:
        raise HTTPException(400, str(e))

    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(400, "ไฟล์ใหญ่เกิน 20MB")

    inbox = root / INBOX
    inbox.mkdir(exist_ok=True)
    safe = _UNSAFE.sub("_", (file.filename or "file").strip()) or "file"
    dest = inbox / safe
    stem, suffix = dest.stem, dest.suffix
    i = 1
    while dest.exists():  # กันชนชื่อ — ไม่ทับของเดิม
        dest = inbox / f"{stem}_{i}{suffix}"
        i += 1
    dest.write_bytes(data)

    rel = dest.relative_to(root).as_posix()
    return {"name": dest.name, "rel": rel, "path": str(dest), "size": len(data)}


@router.get("/files/raw")
def raw_file(path: str):
    """serve ไฟล์ใน workspace (M17-7) — ใช้โชว์รูปที่ generate_image สร้าง (thumbnail ใน sidebar)
    sandbox ผ่าน _resolve เดิม (กัน ../ traversal / absolute หลุด workspace)
    """
    try:
        root = workspace_root()
        fp = _resolve(path, root)
    except WorkspaceError as e:
        raise HTTPException(400, str(e))
    if not fp.is_file():
        raise HTTPException(404, "ไม่พบไฟล์")
    return FileResponse(fp)
