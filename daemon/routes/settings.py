"""/settings — apikey (M1-12), social (M3-10), workspace (M6-6)
apikey เก็บลง daemon/.env เท่านั้น ไม่ log ไม่ broadcast"""
from pathlib import Path
from typing import Optional

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..adapters.llm_adapter import (
    ENV_KEY_MAP, available_cloud_providers, specialist_for)
from ..models.schemas import ApiKeyRequest, SocialSettings, StudioSettings, WorkspaceSettings
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


class KeyAddReq(BaseModel):
    provider: str
    key: str
    label: str = ""


@router.get("/settings/keys")
def list_keys(provider: str = "") -> dict:
    """M11-14 — รายการ cloud key (masked) : default จาก .env + key ใน store; filter ด้วย ?provider"""
    from ..services.cloud_keys import cloud_keys, mask
    out: list[dict] = []
    for prov, env in ENV_KEY_MAP.items():
        if provider and prov != provider:
            continue
        v = os.environ.get(env)
        if v:
            out.append({"id": f"env:{prov}", "provider": prov, "label": "default (.env)",
                        "masked": mask(v), "source": "env"})
        for k in cloud_keys.public_for(prov):
            out.append({**k, "source": "store"})
    return {"keys": out}


@router.post("/settings/keys")
def add_key(payload: KeyAddReq) -> dict:
    """M11-14 — เพิ่ม cloud key ใหม่ (หลายอันต่อ provider ได้) เก็บใน store local เท่านั้น"""
    if payload.provider not in ENV_KEY_MAP:
        raise HTTPException(400, "provider ไม่ถูกต้อง")
    if not payload.key.strip():
        raise HTTPException(400, "ใส่ API key ก่อน")
    from ..services.cloud_keys import cloud_keys
    return cloud_keys.add(payload.provider, payload.label, payload.key)


@router.delete("/settings/keys/{key_id}")
def delete_key(key_id: str) -> dict:
    """M11-14 — ลบ key (env: = เคลียร์ .env default ของ provider, อื่น = ลบจาก store)"""
    from ..services.cloud_keys import cloud_keys
    if key_id.startswith("env:"):
        prov = key_id.split(":", 1)[1]
        env = ENV_KEY_MAP.get(prov)
        if env:
            _write_env_value(env, "")
            os.environ.pop(env, None)
        return {"deleted": key_id}
    if not cloud_keys.delete(key_id):
        raise HTTPException(404, "ไม่พบ key นี้")
    return {"deleted": key_id}


@router.get("/settings/social")
def get_social_settings() -> dict:
    return settings_store.all()


@router.put("/settings/social")
def update_social_settings(payload: SocialSettings) -> dict:
    """มีผลรอบ loop ถัดไปทันที ไม่ต้อง restart daemon"""
    return settings_store.update(payload.model_dump(exclude_none=True))


@router.put("/settings/studio")
def update_studio_settings(payload: StudioSettings) -> dict:
    """M23-1 — ตั้งโดเมน/ภารกิจของออฟฟิศ (มีผลกับงานถัดไปทันที ไม่ต้อง restart)"""
    return settings_store.update(payload.model_dump(exclude_none=True))


class GithubTokenRequest(BaseModel):
    token: str


def _verify_github_token(token: str) -> str:
    """เรียก GitHub /user ด้วย token → คืน login ถ้าใช้ได้ ไม่งั้น raise"""
    import json as _json
    import urllib.request
    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "User-Agent": "ET-Office/0.1"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return _json.loads(r.read().decode()).get("login", "")


@router.post("/settings/github")
def set_github(payload: GithubTokenRequest) -> dict:
    """เก็บ GitHub token (M9-3) — validate กับ GitHub ก่อน แล้วเก็บลง .env เท่านั้น
    token = สิทธิ์เขียน repo จริง → ใช้ fine-grained scope แคบ (Contents/Issues)"""
    token = payload.token.strip()
    if not token:
        raise HTTPException(400, "ใส่ token ก่อน")
    try:
        login = _verify_github_token(token)
    except Exception:
        raise HTTPException(400, "token ใช้ไม่ได้ — เช็ค scope/วันหมดอายุ")
    _write_env_value("GITHUB_TOKEN", token)
    os.environ["GITHUB_TOKEN"] = token   # ให้ subprocess (gh) ใน ToolExecutor ใช้ได้ทันที
    settings_store.update({"github_login": login})
    return {"set": True, "login": login}


@router.get("/settings/github")
def github_status() -> dict:
    """บอกแค่ว่าผูก token แล้วหรือยัง + login + repo — ไม่เปิดเผย token"""
    return {"set": bool(os.environ.get("GITHUB_TOKEN")),
            "login": str(settings_store.get("github_login") or ""),
            "repo": str(settings_store.get("github_repo") or "")}


class GithubRepoRequest(BaseModel):
    repo: str


@router.post("/settings/github-repo")
def set_github_repo(payload: GithubRepoRequest) -> dict:
    """ตั้ง repo เป้าหมาย "owner/name" (M9-4) — validate ว่าเข้าถึงได้ด้วย token ปัจจุบัน"""
    repo = payload.repo.strip().strip("/")
    if repo.count("/") != 1:
        raise HTTPException(400, "รูปแบบ repo ต้องเป็น owner/name")
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise HTTPException(400, "เชื่อม GitHub token ก่อน")
    import json as _json
    import urllib.request
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                     "User-Agent": "ET-Office/0.1"})
        with urllib.request.urlopen(req, timeout=10) as r:
            full = _json.loads(r.read().decode()).get("full_name", repo)
    except Exception:
        raise HTTPException(400, f"เข้าถึง repo ไม่ได้: {repo} (เช็คชื่อ/สิทธิ์ token)")
    settings_store.update({"github_repo": full})
    return {"repo": full}


@router.get("/settings/onboarding")
def get_onboarding() -> dict:
    """sidebar เช็คตอนเปิด — ยังไม่ onboarded → เด้ง wizard สร้าง CEO (M8)"""
    return {"onboarded": bool(settings_store.get("onboarded"))}


@router.post("/settings/onboarding")
def complete_onboarding() -> dict:
    """เรียกหลังสร้าง CEO สำเร็จ — กัน wizard เด้งซ้ำครั้งต่อไป"""
    settings_store.update({"onboarded": True})
    return {"onboarded": True}


@router.get("/settings/specialist")
def specialist_recommendation(role: str = "", keywords: str = "") -> dict:
    """M11-9 — แนะนำ cloud specialist ต่อ role (opt-in banner ตอน hire/gear)

    คืน suggestion + key_available (มี key ของ provider นั้นไหม) + providers ทั้งหมด.
    UI โชว์ banner เฉพาะเมื่อ suggestion ไม่ null และ key_available=True. ไม่เปลี่ยน model เอง.
    """
    kws = [k.strip() for k in keywords.split(",") if k.strip()]
    sug = specialist_for(role, kws)
    providers = available_cloud_providers()
    return {
        "suggestion": sug,
        "key_available": bool(sug and providers.get(sug["provider"])),
        "providers": providers,
    }


class ReviewerSettings(BaseModel):
    enabled: bool


@router.get("/settings/reviewer")
def get_reviewer() -> dict:
    """M11-7 — สถานะ reviewer (เปิด = ตรวจ final รอบ 2 ด้วย same local model)"""
    return {"enabled": bool(settings_store.get("reviewer_enabled"))}


@router.put("/settings/reviewer")
def set_reviewer(payload: ReviewerSettings) -> dict:
    """เปิด/ปิด reviewer (M11-7) — มีผลกับ task ถัดไปทันที"""
    settings_store.update({"reviewer_enabled": payload.enabled})
    return {"enabled": payload.enabled}


class TeamMemoryRequest(BaseModel):
    text: str


@router.get("/settings/team-memory")
def get_team_memory() -> dict:
    """M11-11 — ความจำร่วมของทีม (เป้าหมาย sprint ฯลฯ) ที่ inject ให้ทุก agent"""
    from ..services.memory_service import memory_service
    return {"text": memory_service.team()}


@router.put("/settings/team-memory")
def set_team_memory(payload: TeamMemoryRequest) -> dict:
    """ตั้ง/แก้ความจำร่วมของทีม (M11-11)"""
    from ..services.memory_service import memory_service
    return {"text": memory_service.set_team(payload.text)}


class CostSettings(BaseModel):
    enabled: Optional[bool] = None
    daily_usd: Optional[float] = None
    hourly_usd: Optional[float] = None


@router.get("/settings/cost")
def get_cost() -> dict:
    """M11-10 — สถานะ cost guard (ใช้ไปเท่าไร/เพดาน/เกินไหม)"""
    from ..services.cost_guard import cost_guard
    return cost_guard.status()


@router.put("/settings/cost")
def set_cost(payload: CostSettings) -> dict:
    """ตั้งค่า cost guard (M11-10) — มีผลทันที"""
    changes = {}
    if payload.enabled is not None:
        changes["cost_guard_enabled"] = payload.enabled
    if payload.daily_usd is not None:
        changes["cost_daily_usd"] = max(0.0, payload.daily_usd)
    if payload.hourly_usd is not None:
        changes["cost_hourly_usd"] = max(0.0, payload.hourly_usd)
    settings_store.update(changes)
    from ..services.cost_guard import cost_guard
    return cost_guard.status()


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
