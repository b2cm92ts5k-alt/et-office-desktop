"""/accounts — Provider Accounts (M14-8): api-key + Claude OAuth, ผูกต่อ agent ได้

ยกระดับจาก /settings/keys (M11-14): บัญชี provider 2 โหมด (api_key | oauth) เก็บใน
[[account_store]] (เข้ารหัส DPAPI). secret ไม่เคยส่งออก — list คืน masked เท่านั้น.
"""
from __future__ import annotations

import threading
import webbrowser

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..adapters.llm_adapter import ENV_KEY_MAP, validate_cloud_key
from ..services import oauth_flow
from ..services.account_store import account_store

router = APIRouter(prefix="/accounts", tags=["accounts"])

DAEMON_PORT = 8797  # ต้องตรงกับ uvicorn (main.py) — ใช้ประกอบ loopback redirect ของ OAuth
_REDIRECT_URI = f"http://localhost:{DAEMON_PORT}/accounts/oauth/callback"


@router.get("")
def list_accounts(provider: str = "") -> dict:
    """รายการบัญชี (masked) + บอกว่า provider ไหนรองรับ OAuth/พร้อมใช้ (มี client_id)"""
    return {
        "accounts": account_store.all_public(provider),
        "providers": [
            {"provider": p,
             "oauth": oauth_flow.oauth_supported(p),
             "oauth_ready": oauth_flow.oauth_configured(p)}
            for p in ENV_KEY_MAP
        ],
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


class OAuthStartReq(BaseModel):
    provider: str


@router.post("/oauth/start")
def oauth_start(payload: OAuthStartReq) -> dict:
    """เริ่ม OAuth login (M14-6) — คืน authorize_url + เปิด browser ให้ ผู้ใช้ยินยอมแล้ว
    provider จะ redirect กลับ /accounts/oauth/callback เอง"""
    try:
        out = oauth_flow.start(payload.provider, _REDIRECT_URI)
    except ValueError as e:
        raise HTTPException(400, str(e))
    try:
        webbrowser.open(out["authorize_url"])
        out["browser_opened"] = True
    except Exception:
        out["browser_opened"] = False  # เปิดไม่ได้ → frontend ใช้ url เปิดเอง
    return out


_CALLBACK_HTML = """<!doctype html><meta charset=utf-8><title>ET Office</title>
<body style="font-family:sans-serif;background:#0b0e14;color:#e6e6e6;text-align:center;padding-top:18vh">
<h2 style="color:{color}">{title}</h2><p>{msg}</p><p style="opacity:.6">ปิดหน้าต่างนี้แล้วกลับไปที่ ET Office ได้เลย</p></body>"""


@router.get("/oauth/callback", response_class=HTMLResponse)
def oauth_callback(code: str = "", state: str = "", error: str = "") -> HTMLResponse:
    """provider redirect มาที่นี่ (loopback) → แลก code เป็น token → เก็บเป็น oauth account"""
    if error:
        return HTMLResponse(_CALLBACK_HTML.format(color="#ff6b6b", title="ยกเลิก/ผิดพลาด", msg=error))
    if not code or not state:
        return HTMLResponse(_CALLBACK_HTML.format(color="#ff6b6b", title="ไม่สมบูรณ์", msg="ไม่มี code/state"))
    try:
        provider, tokens = oauth_flow.exchange(state, code)
        account_store.add_oauth(provider, f"{provider} (subscription)", tokens)
    except Exception as e:  # noqa: BLE001
        return HTMLResponse(_CALLBACK_HTML.format(color="#ff6b6b", title="แลก token ไม่สำเร็จ", msg=str(e)[:120]))
    return HTMLResponse(_CALLBACK_HTML.format(color="#51cf66", title="เชื่อมบัญชีสำเร็จ ✓",
                                              msg=f"login {provider} เรียบร้อย"))


@router.delete("/{account_id}")
def delete_account(account_id: str) -> dict:
    if not account_store.delete(account_id):
        raise HTTPException(404, "ไม่พบบัญชีนี้")
    return {"deleted": account_id}
