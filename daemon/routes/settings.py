"""/settings — apikey (M1-12), social (M3-10), workspace (M6-6)
apikey เก็บลง daemon/.env เท่านั้น ไม่ log ไม่ broadcast"""
from pathlib import Path

import os

from fastapi import APIRouter, HTTPException

from ..adapters.llm_adapter import ENV_KEY_MAP
from ..models.schemas import ApiKeyRequest, SocialSettings, WorkspaceSettings
from ..services.settings_store import settings_store

router = APIRouter(tags=["settings"])
ENV_PATH = Path(__file__).parent.parent / ".env"


def _write_env_value(key: str, value: str) -> None:
    lines: list[str] = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    lines = [l for l in lines if not l.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


@router.post("/settings/apikey")
def set_apikey(payload: ApiKeyRequest) -> dict:
    env_var = ENV_KEY_MAP[payload.provider]
    _write_env_value(env_var, payload.key)
    os.environ[env_var] = payload.key   # มีผลทันทีโดยไม่ต้อง restart
    return {"saved": True, "provider": payload.provider}


@router.get("/settings/apikey")
def apikey_status() -> dict:
    """บอกแค่ว่า provider ไหนตั้ง key แล้ว — ไม่เปิดเผยตัว key"""
    return {p: bool(os.environ.get(v)) for p, v in ENV_KEY_MAP.items()}


@router.get("/settings/social")
def get_social_settings() -> dict:
    return settings_store.all()


@router.put("/settings/social")
def update_social_settings(payload: SocialSettings) -> dict:
    """มีผลรอบ loop ถัดไปทันที ไม่ต้อง restart daemon"""
    return settings_store.update(payload.model_dump(exclude_none=True))


@router.get("/settings/workspace")
def get_workspace() -> dict:
    path = str(settings_store.get("workspace_path") or "")
    return {"path": path, "valid": bool(path) and Path(path).is_dir()}


@router.put("/settings/workspace")
def set_workspace(payload: WorkspaceSettings) -> dict:
    """ตั้งโฟลเดอร์ workspace ทีม (M6-6) — "" = ปิด tool use กลับเป็นแชทอย่างเดียว"""
    path = payload.path.strip()
    if path and not Path(path).is_dir():
        raise HTTPException(400, f"ไม่พบโฟลเดอร์: {path}")
    settings_store.update({"workspace_path": path})
    return {"path": path, "valid": bool(path)}
