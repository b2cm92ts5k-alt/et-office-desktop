"""/skills (M15-3) — ดู + เปิด/ปิด skill (สูตรทำงานที่ inject ให้ sub-agent)"""
from fastapi import APIRouter
from pydantic import BaseModel

from ..services.skill_service import skill_service

router = APIRouter(tags=["skills"])


@router.get("/skills")
def list_skills() -> dict:
    return {"skills": skill_service.public_list()}


class SkillToggle(BaseModel):
    enabled: bool


@router.put("/skills/{name}")
def toggle_skill(name: str, payload: SkillToggle) -> dict:
    return {"name": name, "enabled": skill_service.set_enabled(name, payload.enabled)}
