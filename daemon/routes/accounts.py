"""/accounts — Provider Accounts (M14): api-key accounts (เข้ารหัส DPAPI)

ยกระดับจาก /settings/keys (M11-14): บัญชี provider เก็บใน [[account_store]] (เข้ารหัส DPAPI).
secret ไม่เคยส่งออก — list คืน masked เท่านั้น.

หมายเหตุ: OAuth (login subscription) ถูกถอดออก — Anthropic/Google ห้าม third-party app ใช้
OAuth ของ subscription (ผิด ToS). ทางที่ถูกกฎ = API key. ดู [[et-office-m14-provider-accounts]].
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..adapters.llm_adapter import ENV_KEY_MAP, validate_cloud_key
from ..services.account_store import account_store, mask

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("")
def list_accounts(provider: str = "") -> dict:
    """รายการ credential ทุกแหล่ง (masked): account_store (DPAPI) + default จาก .env

    รวม .env เข้ามาด้วย (เหมือน M11-14) ไม่งั้น key ที่ตั้งใน .env จะมองไม่เห็น/ลบไม่ได้
    แต่ /models/available ยังเห็น → model โผล่ทั้งที่ UI ว่าง (bug).
    """
    accounts = list(account_store.all_public(provider))
    for prov, env in ENV_KEY_MAP.items():
        if provider and prov != provider:
            continue
        v = os.environ.get(env)
        if v:
            accounts.append({"id": f"env:{prov}", "provider": prov, "label": "default (.env)",
                             "auth_mode": "env", "masked": mask(v)})
    return {"accounts": accounts, "providers": [{"provider": p} for p in ENV_KEY_MAP]}


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
    models: list[dict] = []
    if payload.validate:
        res = validate_cloud_key(payload.provider, key)
        if not res.get("ok"):
            raise HTTPException(400, f"key ใช้ไม่ได้: {res.get('error', 'unknown')}")
        models = res.get("models", [])
    # M16-3: persist ลิสต์ที่ validate ดึงมา (ถ้า validate=False → models=None ไม่ cache)
    acc = account_store.add_api_key(payload.provider, payload.label, key,
                                    models if payload.validate else None)
    return {**acc, "validated": payload.validate, "models_count": len(models)}


def _provider_key(account_id: str) -> tuple[str, str, dict | None]:
    """หา (provider, key, account|None) จาก account_id — รองรับ env:<provider> ด้วย (M16-3)"""
    if account_id.startswith("env:"):
        prov = account_id.split(":", 1)[1]
        key = os.environ.get(ENV_KEY_MAP.get(prov, "") or "", "")
        if not key:
            raise HTTPException(404, "ไม่พบ key ของ .env นี้")
        return prov, key, None
    acc = account_store.get(account_id)
    if not acc:
        raise HTTPException(404, "ไม่พบบัญชีนี้")
    return acc["provider"], acc.get("secret", {}).get("key", ""), acc


@router.post("/{account_id}/refresh-models")
def refresh_models(account_id: str) -> dict:
    """ดึงรายชื่อ model ของ key นี้ใหม่ → อัปเดต cache + คืน diff (M16-3)

    ผู้ใช้กดเอง (ไม่ auto). UI ใช้ added/removed โชว์ toast "พบ N ใหม่". env:<provider>
    ดึงสดได้แต่ไม่ persist (ไม่มี record ให้เก็บ).
    """
    prov, key, acc = _provider_key(account_id)
    old_ids = {m.get("id") for m in (acc.get("models") if acc else None) or []}
    res = validate_cloud_key(prov, key)
    if not res.get("ok"):
        raise HTTPException(400, f"ดึงรายชื่อ model ไม่ได้: {res.get('error', 'unknown')}")
    models = res.get("models", [])
    new_ids = {m.get("id") for m in models}
    if acc is not None:
        account_store.set_models(account_id, models)
    return {"total": len(models),
            "chat": sum(1 for m in models if m.get("kind") == "chat"),
            "added": sorted(i for i in (new_ids - old_ids) if i),
            "removed": sorted(i for i in (old_ids - new_ids) if i)}


@router.get("/{account_id}/models")
def account_models(account_id: str, show_all: bool = Query(False, alias="all")) -> dict:
    """ลิสต์ model ของ account จาก cache (M16-3) — default เฉพาะ chat; ?all=1 = ทุก kind

    env:<provider> ไม่มี cache → ดึงสด (UI "แสดงทั้งหมด" ของ account .env)
    """
    if account_id.startswith("env:"):
        prov, key, _ = _provider_key(account_id)
        res = validate_cloud_key(prov, key)
        models = res.get("models", []) if res.get("ok") else []
    else:
        acc = account_store.get(account_id)
        if not acc:
            raise HTTPException(404, "ไม่พบบัญชีนี้")
        models = list(acc.get("models") or [])
    if not show_all:
        models = [m for m in models if m.get("kind") == "chat"]
    return {"models": models, "total": len(models)}


@router.delete("/{account_id}")
def delete_account(account_id: str) -> dict:
    # env:<provider> = เคลียร์ key default ใน .env (มีผลทันที)
    if account_id.startswith("env:"):
        prov = account_id.split(":", 1)[1]
        env = ENV_KEY_MAP.get(prov)
        if not env:
            raise HTTPException(404, "provider ไม่ถูกต้อง")
        from .settings import _write_env_value
        _write_env_value(env, "")
        os.environ.pop(env, None)
        return {"deleted": account_id}
    if not account_store.delete(account_id):
        raise HTTPException(404, "ไม่พบบัญชีนี้")
    return {"deleted": account_id}
