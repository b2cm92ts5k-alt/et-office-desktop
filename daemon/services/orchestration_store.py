"""OrchestrationStore (M21-1) — เก็บสถานะงาน orchestration ล่าสุด

CEO: สั่ง "ทำงานต่อจากเดิม" แล้วระบบทำใหม่ทั้งชุด → เก็บสถานะแต่ละขั้น (✅/❌/⏭️/⚠️ + output)
ของงานที่ Producer แตก เพื่อให้ปุ่ม "▶️ ทำต่อ" รันเฉพาะขั้นที่ยังไม่ done (ไม่ทำซ้ำ).

เก็บเป็น JSON file เดียวกับ store อื่น ๆ (settings/account) — list ล่าสุดก่อน, cap MAX_KEEP.
เก็บแค่ข้อมูลพอทำต่อ (subtask/agent/status/output ย่อ) ไม่เก็บ secret/log ดิบ.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
STORE = DATA_DIR / "orchestrations.json"
MAX_KEEP = 30          # งานล่าสุดกี่ชุดที่ยอมจำไว้ให้ทำต่อ
OUTPUT_CLIP = 1500     # ย่อ output ต่อขั้น กันไฟล์บวม (ทำต่อใช้เป็น context เท่านั้น)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OrchestrationStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def _read(self) -> list[dict]:
        try:
            return json.loads(STORE.read_text(encoding="utf-8")).get("items", [])
        except Exception:  # noqa: BLE001 — ไฟล์ไม่มี/พัง = ยังไม่มีงานที่จำไว้
            return []

    def _write(self, items: list[dict]) -> None:
        DATA_DIR.mkdir(exist_ok=True)
        STORE.write_text(
            json.dumps({"items": items[:MAX_KEEP]}, ensure_ascii=False, indent=1),
            encoding="utf-8")

    def save(self, task_id: str, message: str, steps: list[dict]) -> None:
        """บันทึก/ทับสถานะของ task นี้. steps = list[{role, subtask, agent_id, agent_name, status, output}]"""
        clean = [{
            "role": str(s.get("role", "")),
            "subtask": str(s.get("subtask", "")),
            "agent_id": str(s.get("agent_id", "")),
            "agent_name": str(s.get("agent_name", "")),
            "status": str(s.get("status", "done")),
            "output": str(s.get("output", ""))[:OUTPUT_CLIP],
        } for s in steps]
        done = sum(1 for s in clean if s["status"] == "done")
        entry = {
            "task_id": task_id, "message": message, "updated_at": _now(),
            "done": done, "total": len(clean), "pending": len(clean) - done,
            "steps": clean,
        }
        with self._lock:
            items = [it for it in self._read() if it.get("task_id") != task_id]
            items.insert(0, entry)
            self._write(items)

    def get(self, task_id: str) -> dict | None:
        for it in self._read():
            if it.get("task_id") == task_id:
                return it
        return None

    def latest(self) -> dict | None:
        items = self._read()
        return items[0] if items else None

    def list(self, limit: int = 20) -> list[dict]:
        """สรุป (ไม่มี steps เต็ม) — UI แสดงรายการงานที่ทำต่อได้"""
        keys = ("task_id", "message", "updated_at", "done", "total", "pending")
        return [{k: it.get(k) for k in keys} for it in self._read()[:limit]]


orchestration_store = OrchestrationStore()
