"""OAuth (PKCE / RFC 8252) สำหรับ login บัญชี subscription (M14-6)

เคสจริงที่ใช้ได้: **Claude (Anthropic) Pro/Max** — กลไกเดียวกับ Claude Code "Sign in with Claude":
ผู้ใช้กดปุ่ม → เปิด browser ไปหน้า authorize ของผู้ให้บริการ → ยินยอม → redirect กลับ
loopback (`http://localhost:<daemon_port>/accounts/oauth/callback`) พร้อม `code` → daemon แลก
`code`+`code_verifier` เป็น token → เก็บใน [[account_store]] (เข้ารหัส DPAPI) เป็น oauth account.

PKCE (S256) บังคับใช้ — public client บนเครื่อง user ไม่มี client_secret ปลอดภัย.

⚠️ **ต้องลงทะเบียน OAuth client กับผู้ให้บริการก่อน** แล้วใส่ `client_id` (+ endpoint/scope ที่ถูกต้อง)
ผ่าน env. ค่า default ด้านล่างเป็นโครงตามที่เปิดเผยของ Claude Code — **ยืนยัน/อัปเดตกับเอกสาร
Anthropic ปัจจุบันก่อน production**. กลไก PKCE/exchange/refresh ด้านล่างเป็นมาตรฐาน ทำงานได้ทันที
เมื่อใส่ค่า config ที่ถูกต้อง.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.parse
import urllib.request

# config ต่อ provider — เปิดทาง env override (CEO ใส่ค่าที่ลงทะเบียนเองได้โดยไม่แก้โค้ด)
PROVIDER_OAUTH: dict[str, dict] = {
    "claude": {
        "authorize_url": os.environ.get("ET_CLAUDE_OAUTH_AUTHORIZE", "https://claude.ai/oauth/authorize"),
        "token_url": os.environ.get("ET_CLAUDE_OAUTH_TOKEN", "https://console.anthropic.com/v1/oauth/token"),
        "client_id": os.environ.get("ET_CLAUDE_OAUTH_CLIENT_ID", ""),  # ต้องลงทะเบียน
        "scope": os.environ.get("ET_CLAUDE_OAUTH_SCOPE", "org:create_api_key user:profile user:inference"),
    },
}

# pending flow ที่รอ callback: state -> {provider, verifier, redirect_uri, created}
_pending: dict[str, dict] = {}
_lock = threading.Lock()
_PENDING_TTL = 600  # 10 นาที — เกินกว่านี้ทิ้ง (กัน state ค้าง)


def oauth_supported(provider: str) -> bool:
    return provider in PROVIDER_OAUTH


def oauth_configured(provider: str) -> bool:
    """พร้อมใช้จริงไหม (มี client_id ที่ลงทะเบียนแล้ว)"""
    c = PROVIDER_OAUTH.get(provider)
    return bool(c and c.get("client_id"))


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def pkce_pair() -> tuple[str, str]:
    """(code_verifier, code_challenge S256) ตาม RFC 7636"""
    verifier = _b64url(secrets.token_bytes(64))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def _prune() -> None:
    now = time.time()
    for s in [s for s, v in _pending.items() if now - v["created"] > _PENDING_TTL]:
        _pending.pop(s, None)


def start(provider: str, redirect_uri: str) -> dict:
    """เริ่ม flow: สร้าง state+PKCE, จำ pending, คืน authorize_url ให้เปิด browser (M14-6)"""
    cfg = PROVIDER_OAUTH.get(provider)
    if not cfg:
        raise ValueError(f"provider '{provider}' ไม่รองรับ OAuth")
    if not cfg.get("client_id"):
        raise ValueError(f"ยังไม่ได้ตั้ง OAuth client_id ของ {provider} — ลงทะเบียน client แล้วใส่ค่าก่อน")
    verifier, challenge = pkce_pair()
    state = _b64url(secrets.token_bytes(24))
    with _lock:
        _prune()
        _pending[state] = {"provider": provider, "verifier": verifier,
                           "redirect_uri": redirect_uri, "created": time.time()}
    params = {
        "response_type": "code",
        "client_id": cfg["client_id"],
        "redirect_uri": redirect_uri,
        "scope": cfg["scope"],
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return {"authorize_url": f"{cfg['authorize_url']}?{urllib.parse.urlencode(params)}", "state": state}


def _post_token(token_url: str, data: dict, timeout: int = 20) -> dict:
    req = urllib.request.Request(
        token_url,
        data=urllib.parse.urlencode(data).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _normalize(tok: dict) -> dict:
    """แปลง token response → รูปแบบที่ account_store เก็บ (คำนวณ expires_at จาก expires_in)"""
    exp_in = float(tok.get("expires_in", 0) or 0)
    return {
        "access_token": tok.get("access_token", ""),
        "refresh_token": tok.get("refresh_token", ""),
        "expires_at": (time.time() + exp_in) if exp_in else 0.0,
        "scope": tok.get("scope", ""),
    }


def exchange(state: str, code: str) -> tuple[str, dict]:
    """แลก authorization code → token (เรียกจาก callback). คืน (provider, normalized_tokens).

    ตรวจ state ตรง pending (กัน CSRF) + ใช้ code_verifier ที่ผูกไว้ (PKCE).
    """
    with _lock:
        pend = _pending.pop(state, None)
    if not pend:
        raise ValueError("state ไม่ถูกต้องหรือหมดอายุ — เริ่ม login ใหม่")
    provider = pend["provider"]
    cfg = PROVIDER_OAUTH[provider]
    tok = _post_token(cfg["token_url"], {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": cfg["client_id"],
        "redirect_uri": pend["redirect_uri"],
        "code_verifier": pend["verifier"],
    })
    return provider, _normalize(tok)


def refresh(provider: str, refresh_token: str) -> dict:
    """ขอ access token ใหม่ด้วย refresh token (M14-7) — คืน normalized tokens"""
    cfg = PROVIDER_OAUTH.get(provider)
    if not cfg:
        raise ValueError(f"provider '{provider}' ไม่รองรับ OAuth")
    tok = _post_token(cfg["token_url"], {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": cfg["client_id"],
    })
    return _normalize(tok)
