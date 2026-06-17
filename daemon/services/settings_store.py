"""SettingsStore — ค่า config ปรับได้ runtime เก็บเป็น JSON file (M3-10)
ตอนนี้มีเฉพาะกลุ่ม social/proposal — เพิ่ม key ใหม่ที่ DEFAULTS ที่เดียว
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

SETTINGS_PATH = Path(__file__).parent.parent / "data" / "settings.json"

DEFAULTS: dict = {
    "social_enabled": True,
    "social_interval_sec": 300,      # เช็คทุก 5 นาที (blueprint)
    "social_chance": 0.3,            # 30% ต่อรอบ
    "proposal_cooldown_sec": 1800,   # ห่างขั้นต่ำระหว่าง proposal 30 นาที
    "workspace_path": "",            # โฟลเดอร์ workspace ทีม (M6-6) — "" = ปิด tool use
    "installed_models": [],          # local model ที่ลงผ่าน Model Manager (M7-3) — cap 1 ตัว
    "active_local_model": "",        # local tag เดียวที่ทุก ollama agent ใช้ (M7-8); "" = ใช้ VRAMDetector recommended — กันรัน 2 ตัวพร้อมกัน
    "onboarded": False,              # ผ่าน onboarding สร้าง CEO แล้วหรือยัง (M8)
    "github_login": "",              # username ที่ผูก GitHub token ไว้ (M9-3) — token เก็บใน .env
    "github_repo": "",               # repo เป้าหมายของทีม "owner/name" (M9-4)
    "mcp_servers": [],               # MCP servers [{name, command, enabled}] (M10)
    "reviewer_enabled": False,       # M11-7 — reviewer รอบ 2 (same local model) ตรวจ final ก่อนส่ง; ปิดไว้กันงานเร็วเปลือง
    "cost_guard_enabled": True,      # M11-10 — เปิด guard ค่า cloud
    "cost_daily_usd": 5.0,           # M11-10 — เพดานต่อวัน (USD); 0 = ไม่จำกัด
    "cost_hourly_usd": 0.0,          # M11-10 — เพดานต่อชั่วโมง (USD); 0 = ไม่จำกัด
}


class SettingsStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict = dict(DEFAULTS)
        if SETTINGS_PATH.exists():
            try:
                saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                self._values.update({k: saved[k] for k in DEFAULTS if k in saved})
            except (json.JSONDecodeError, OSError):
                pass  # ไฟล์พัง → ใช้ default แล้วเขียนทับตอน update ครั้งถัดไป

    def all(self) -> dict:
        return dict(self._values)

    def get(self, key: str):
        return self._values.get(key, DEFAULTS.get(key))

    def update(self, changes: dict) -> dict:
        """รับเฉพาะ key ที่รู้จัก — กัน typo เขียนค่าขยะลงไฟล์"""
        with self._lock:
            self._values.update({k: v for k, v in changes.items()
                                 if k in DEFAULTS and v is not None})
            SETTINGS_PATH.parent.mkdir(exist_ok=True)
            SETTINGS_PATH.write_text(
                json.dumps(self._values, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return dict(self._values)


settings_store = SettingsStore()
