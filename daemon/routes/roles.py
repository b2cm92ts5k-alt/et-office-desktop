"""/roles — preset roles + .md upload (M1-10)"""
from fastapi import APIRouter, HTTPException, UploadFile

from ..models.schemas import RolePreset
from ..services.role_parser import load_preset_roles, parse_role_md

router = APIRouter(tags=["roles"])


@router.get("/roles")
def list_roles() -> list[RolePreset]:
    return load_preset_roles()


@router.post("/roles/upload")
async def upload_role(file: UploadFile) -> RolePreset:
    if not (file.filename or "").endswith(".md"):
        raise HTTPException(400, "ต้องเป็นไฟล์ .md เท่านั้น")
    text = (await file.read()).decode("utf-8", errors="replace")
    return parse_role_md(text, file.filename or "uploaded.md")
