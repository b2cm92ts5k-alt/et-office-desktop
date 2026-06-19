"""/accounts — Provider Accounts (M14): api-key accounts (เข้ารหัส DPAPI)

ยกระดับจาก /settings/keys (M11-14): บัญชี provider เก็บใน [[account_store]] (เข้ารหัส DPAPI).
secret ไม่เคยส่งออก — list คืน masked เท่านั้น.

หมายเหตุ: OAuth (login subscription) ถูกถอดออก — Anthropic/Google ห้าม third-party app ใช้
OAuth ของ subscription (ผิด ToS). ทางที่ถูกกฎ = API key. ดู [[et-office-m14-provider-accounts]].
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..adapters.llm_adapter import ENV_KEY_MAP, validate_cloud_key
from ..services.account_store import account_store

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("")
def list_accounts(provider: str = "") -> dict:
    """รายการบัญชี (masked) + provider ที่รองรับ"""
    return {
        "accounts": account_store.all_public(provider),
        "providers": [{"provider": p} for p in ENV_KEY_MAP],
    }


class ApiKeyAccountReq(BaseModel):
    provider: str
    key: str
    label: str = ""
    validate: bool = True   # ปิดได้ถ้า offline/ไม่อยาก ping


@router.post("/api-key")
def add_api_key_account(payload: ApiKeyAccountReq) -> dict:
    """เพิ่มบัญชีแบบ API key (M14-5) — validate กับ provider จริงก่อน (default) แล้วเก็บ"""
    if payload.provider not in ENV_KEY_MAP:
        raise HTTPException(400, "provider ไม่ถูกต้อง")
    key = payload.key.strip()
    if not key:
        raise HTTPException(400, "ใส่ API key ก่อน")
    models: list[str] = []
    if payload.validate:
        res = validate_cloud_key(payload.provider, key)
        if not res.get("ok"):
            raise HTTPException(400, f"key ใช้ไม่ได้: {res.get('error', 'unknown')}")
        models = res.get("models", [])
    acc = account_store.add_api_key(payload.provider, payload.label, key)
    return {**acc, "validated": payload.validate, "models": models}


@router.delete("/{account_id}")
def delete_account(account_id: str) -> dict:
    if not account_store.delete(account_id):
        raise HTTPException(404, "ไม่พบบัญชีนี้")
    return {"deleted": account_id}
