"""ProviderAccountStore (M14-1) — บัญชี API key ต่อ provider เข้ารหัส DPAPI

ยกระดับจาก [[cloud_keys]] (CloudKeyStore): เก็บเป็น "บัญชี" (account) แบบ api_key
  - auth_mode="api_key" : secret = {"key": "..."} (วาง key เอง — claude/gemini/openai/grok/deepseek)

(OAuth/subscription login ถอดออก — Anthropic/Google ห้าม third-party ใช้ OAuth ของ subscription
ผิด ToS เสี่ยงแบน. ทางที่ถูก = API key. ดู [[et-office-m14-provider-accounts]].)

privacy (คงกฎเดิม): secret อยู่แค่ไฟล์ local นี้ + **เข้ารหัส DPAPI at rest** (ผูก Windows user)
— agent เก็บแค่ `account_id` อ้างอิง ไม่เก็บ secret; ที่ส่งออก API ปิดบัง (masked) ไม่เคยคาย key ดิบ.

ไฟล์: data/cloud_accounts.enc (DPAPI blob, gitignored). ถ้า DPAPI ใช้ไม่ได้ (ไม่ใช่ Windows /
ไม่มี pywin32) → fallback เก็บ plaintext data/cloud_accounts.json + เตือน (dev เท่านั้น).

migration: รอบแรกถ้ายังไม่มีไฟล์ account แต่มี cloud_keys.json เดิม → import เป็น api_key accounts.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from uuid import uuid4

_DATA_DIR = Path(__file__).parent.parent / "data"
ENC_PATH = _DATA_DIR / "cloud_accounts.enc"      # DPAPI-encrypted (ปกติ)
PLAIN_PATH = _DATA_DIR / "cloud_accounts.json"   # fallback ถ้า DPAPI ใช้ไม่ได้
LEGACY_KEYS_PATH = _DATA_DIR / "cloud_keys.json"  # ของเดิม (M11-14) — ใช้ migrate


def mask(secret: str) -> str:
    """ปิดบังเหลือ 4 ตัวท้าย — โชว์ใน UI/API (ไม่คายตัวเต็ม)"""
    s = str(secret or "")
    return ("…" + s[-4:]) if len(s) >= 4 else "…"


def _dpapi():
    """คืน module win32crypt ถ้าใช้ DPAPI ได้ ไม่งั้น None (fallback plaintext)"""
    try:
        import win32crypt  # type: ignore
        return win32crypt
    except Exception:
        return None


class ProviderAccountStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._accounts: list[dict] = []   # [{id, provider, label, auth_mode, secret:{...}, created_at}]
        self._load()

    # ---- persistence (DPAPI) ----
    def _encrypt(self, raw: bytes) -> bytes | None:
        w = _dpapi()
        if w is None:
            return None
        # description "ET-Office accounts" + CRYPTPROTECT_UI_FORBIDDEN(0) ผูก current user
        return w.CryptProtectData(raw, "ET-Office accounts", None, None, None, 0)

    def _decrypt(self, blob: bytes) -> bytes:
        w = _dpapi()
        if w is None:
            raise RuntimeError("DPAPI unavailable แต่ไฟล์ encrypted")
        return w.CryptUnprotectData(blob, None, None, None, 0)[1]

    def _load(self) -> None:
        try:
            if ENC_PATH.exists():
                self._accounts = json.loads(self._decrypt(ENC_PATH.read_bytes()).decode("utf-8"))
                return
            if PLAIN_PATH.exists():
                self._accounts = json.loads(PLAIN_PATH.read_text(encoding="utf-8"))
                return
        except (json.JSONDecodeError, OSError, RuntimeError):
            self._accounts = []
            return
        # ไม่มีไฟล์ account → ลอง migrate จาก cloud_keys.json เดิม (ครั้งเดียว)
        self._migrate_legacy()

    def _save(self) -> None:
        _DATA_DIR.mkdir(exist_ok=True)
        raw = json.dumps(self._accounts, ensure_ascii=False, indent=2).encode("utf-8")
        blob = self._encrypt(raw)
        if blob is not None:
            ENC_PATH.write_bytes(blob)
            PLAIN_PATH.unlink(missing_ok=True)   # กันคู่ plaintext ค้าง
        else:
            # dev fallback — ไม่มี DPAPI: เก็บ plaintext (gitignored) + ไม่มี blob
            PLAIN_PATH.write_text(raw.decode("utf-8"), encoding="utf-8")

    def _migrate_legacy(self) -> None:
        """import cloud_keys.json (M11-14) → api_key accounts — รักษา id เดิมไว้ให้ key_id ยังตรง"""
        if not LEGACY_KEYS_PATH.exists():
            return
        try:
            old = json.loads(LEGACY_KEYS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for k in old:
            if not k.get("key"):
                continue
            self._accounts.append({
                "id": k.get("id") or uuid4().hex[:8],
                "provider": k.get("provider", ""),
                "label": k.get("label", "") or "key",
                "auth_mode": "api_key",
                "secret": {"key": k["key"]},
                "created_at": time.time(),
            })
        if self._accounts:
            self._save()

    # ---- queries ----
    def all_public(self, provider: str = "") -> list[dict]:
        """รายการ masked สำหรับ UI/API (ไม่มี secret) — filter ด้วย provider ได้"""
        out = []
        for a in self._accounts:
            if provider and a.get("provider") != provider:
                continue
            out.append(self._public(a))
        return out

    def accounts_for(self, provider: str) -> list[dict]:
        """entry เต็ม (มี secret) ของ provider — ฝั่ง server เท่านั้น"""
        return [a for a in self._accounts if a.get("provider") == provider]

    def _public(self, a: dict) -> dict:
        sec = a.get("secret", {})
        return {"id": a["id"], "provider": a["provider"], "label": a.get("label", ""),
                "auth_mode": a.get("auth_mode", "api_key"), "masked": mask(sec.get("key", ""))}

    def get(self, account_id: str) -> dict | None:
        """คืน account เต็ม (มี secret) — ใช้ตอน resolve ค่า cloud call (get_llm)"""
        for a in self._accounts:
            if a["id"] == account_id:
                return a
        return None

    # ---- mutations ----
    def add_api_key(self, provider: str, label: str, key: str) -> dict:
        entry = {"id": uuid4().hex[:8], "provider": provider,
                 "label": (label or "").strip() or "key", "auth_mode": "api_key",
                 "secret": {"key": key.strip()}, "created_at": time.time()}
        with self._lock:
            self._accounts.append(entry)
            self._save()
        return self._public(entry)

    def delete(self, account_id: str) -> bool:
        with self._lock:
            before = len(self._accounts)
            self._accounts = [a for a in self._accounts if a["id"] != account_id]
            if len(self._accounts) == before:
                return False
            self._save()
            return True


account_store = ProviderAccountStore()
