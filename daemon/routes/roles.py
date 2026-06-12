"""/roles — preset roles + .md upload (M1-10) + AI draft / save (M6-2, M6-3)"""
import asyncio
import re

from fastapi import APIRouter, HTTPException, UploadFile

from ..adapters.llm_adapter import get_llm
from ..models.schemas import LLMConfig, RoleDraftRequest, RolePreset, RoleSaveRequest
from ..services.role_parser import ROLES_DIR, load_preset_roles, parse_role_md

router = APIRouter(tags=["roles"])

# M6-3 — prompt ร่าง role .md (format ตรงกับ RoleParser M1-10)
DRAFT_PROMPT = """คุณคือ HR ของสตูดิโอ ET Office หน้าที่คือเขียนไฟล์ role .md ให้ AI agent ใหม่
จากคำอธิบายหน้าที่: "{description}"

ตอบเป็นเนื้อหาไฟล์ .md เท่านั้น ห้ามมีคำอธิบายอื่น ห้ามครอบด้วย ``` รูปแบบ:
---
name: <ชื่อ agent ขึ้นต้นด้วย ET เช่น ET Writer>
role: <ตำแหน่งภาษาอังกฤษสั้น ๆ>
avatar: "<emoji 1 ตัว>"
color: "<เลือกจาก #e040fb #00e5ff #ff4da6 #00ff9f #ffe040 #ff6030>"
keywords: [<5-8 คำไทย/อังกฤษ ที่ใช้ route งานมาหา agent นี้>]
---
<system prompt ภาษาไทย 4-8 บรรทัด: บทบาท ความเชี่ยวชาญ วิธีตอบ ขอบเขตงานที่รับ/ไม่รับ>"""


def _clean_draft(text: str) -> str:
    """ตัด <think> ของ qwen3 + code fence + ข้อความนำหน้า frontmatter"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    fence = re.search(r"```(?:markdown|md)?\s*(.*?)```", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start = text.find("---")
    if start > 0:
        text = text[start:]
    return text.strip()


@router.get("/roles")
def list_roles() -> list[RolePreset]:
    return load_preset_roles()


@router.post("/roles/upload")
async def upload_role(file: UploadFile) -> RolePreset:
    if not (file.filename or "").endswith(".md"):
        raise HTTPException(400, "ต้องเป็นไฟล์ .md เท่านั้น")
    text = (await file.read()).decode("utf-8", errors="replace")
    return parse_role_md(text, file.filename or "uploaded.md")


@router.post("/roles/draft")
async def draft_role(payload: RoleDraftRequest) -> dict:
    """M6-3 — LLM ร่าง role .md จากคำอธิบายสั้น ๆ (ใช้ model default = ollama local)"""
    description = payload.description.strip()
    if not description:
        raise HTTPException(400, "ต้องมีคำอธิบายหน้าที่")
    llm = get_llm(LLMConfig())
    raw = await asyncio.to_thread(llm.call, DRAFT_PROMPT.format(description=description))
    text = _clean_draft(str(raw))
    if not text.startswith("---"):
        raise HTTPException(502, "LLM ตอบไม่ตรง format — ลองใหม่อีกครั้ง")
    return {"text": text}


@router.post("/roles/save")
def save_role(payload: RoleSaveRequest) -> RolePreset:
    """M6-2 — บันทึก .md ลง daemon/roles/ ให้โผล่ใน GET /roles ใช้ซ้ำได้"""
    text = payload.text.strip()
    if not text:
        raise HTTPException(400, "ไฟล์ว่าง")
    preset = parse_role_md(text, payload.filename or "custom.md")
    stem_src = payload.filename.removesuffix(".md") if payload.filename else preset.name
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", stem_src).strip("-").lower() or "custom"
    ROLES_DIR.mkdir(exist_ok=True)
    path = ROLES_DIR / f"{stem}.md"
    path.write_text(text, encoding="utf-8")
    preset.file = path.name
    return preset
