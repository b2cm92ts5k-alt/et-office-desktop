"""/settings/apikey — เก็บ key ลง daemon/.env เท่านั้น ไม่ log ไม่ broadcast (M1-12)"""
from pathlib import Path

import os

from fastapi import APIRouter

from ..adapters.llm_adapter import ENV_KEY_MAP
from ..models.schemas import ApiKeyRequest

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
