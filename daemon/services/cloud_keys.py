"""CloudKeyStore (M11-14) — เก็บหลาย API key ต่อ provider (เลือกใช้ต่อ agent ได้)

เดิมเก็บ key 1 อันต่อ provider ใน `.env` — ตัวนี้ให้เก็บได้หลายอัน (มี label) เพื่อให้
agent คนละตัวใช้คนละ key/รุ่นได้ (กระจายโควต้า/กัน rate limit) — เป็น optional.

privacy: secret อยู่แค่ไฟล์ local นี้ (gitignored) — agent เก็บแค่ `key_id` อ้างอิง,
ไม่เก็บ secret; list ที่ส่งออกผ่าน API ปิดบัง (masked) ไม่เคยคาย key ดิบ/ไม่ log.
`.env` ยังเป็น "default" ต่อ provider (agent ไม่มี key_id ใช้ตัวนั้น) — backward compat.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from uuid import uuid4

KEYS_PATH = Path(__file__).parent.parent / "data" / "cloud_keys.json"


def mask(key: str) -> str:
    """ปิดบัง key เหลือ 4 ตัวท้าย — ใช้โชว์ใน UI/API (ไม่คายตัวเต็ม)"""
    k = str(key or "")
    return ("…" + k[-4:]) if len(k) >= 4 else "…"


class CloudKeyStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._keys: list[dict] = []   # [{id, provider, label, key}]
        self._load()

    def _load(self) -> None:
        if KEYS_PATH.exists():
            try:
                self._keys = json.loads(KEYS_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._keys = []

    def _save(self) -> None:
        KEYS_PATH.parent.mkdir(exist_ok=True)
        KEYS_PATH.write_text(json.dumps(self._keys, ensure_ascii=False, indent=2), encoding="utf-8")

    def keys_for(self, provider: str) -> list[dict]:
        """entry เต็ม (มี key) ของ provider — ใช้ฝั่ง server เท่านั้น (get_llm)"""
        return [k for k in self._keys if k.get("provider") == provider]

    def public_for(self, provider: str) -> list[dict]:
        """รายการ masked สำหรับ UI/API (ไม่มี secret)"""
        return [{"id": k["id"], "provider": k["provider"], "label": k.get("label", ""),
                 "masked": mask(k.get("key", ""))} for k in self.keys_for(provider)]

    def get(self, key_id: str) -> str | None:
        for k in self._keys:
            if k["id"] == key_id:
                return k.get("key", "")
        return None

    def add(self, provider: str, label: str, key: str) -> dict:
        entry = {"id": uuid4().hex[:8], "provider": provider,
                 "label": (label or "").strip() or "key", "key": key.strip()}
        with self._lock:
            self._keys.append(entry)
            self._save()
        return {"id": entry["id"], "provider": provider, "label": entry["label"],
                "masked": mask(entry["key"])}

    def delete(self, key_id: str) -> bool:
        with self._lock:
            before = len(self._keys)
            self._keys = [k for k in self._keys if k["id"] != key_id]
            if len(self._keys) == before:
                return False
            self._save()
            return True


cloud_keys = CloudKeyStore()
