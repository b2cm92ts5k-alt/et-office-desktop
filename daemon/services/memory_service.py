"""MemoryService (M11-11, §4.4) — memory แยกต่อ agent + team memory ร่วม

เดิมทุก task เริ่ม context สด ไม่มีความจำข้ามงาน. ตัวนี้เพิ่ม:
- **per-agent memory**: note สั้น ๆ ของแต่ละ agent (จำงานที่ตัวเองเคยทำ) — designer ไม่เห็นของ coder
- **team memory**: เรื่องที่ทั้งทีมต้องรู้ร่วมกัน (เป้าหมาย sprint, ข้อตกลง) — CEO ตั้งเองได้

เก็บเป็น JSON file. inject เข้า system prompt ตอนรัน + เขียน note กลับหลัง task เสร็จ.
MVP: per-agent = สรุปงานล่าสุด N บรรทัด (ไม่ใช่ vector memory เต็มรูปแบบ — ไว้ขยายทีหลัง).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

MEMORY_PATH = Path(__file__).parent.parent / "data" / "memory.json"
NOTES_PER_AGENT = 8       # เก็บ note ล่าสุดต่อ agent กี่บรรทัด (กัน context บวม)
NOTE_MAX_CHARS = 200      # ความยาวต่อ note


class MemoryService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._team: str = ""
        self._agents: dict[str, list[str]] = {}
        self._load()

    def _load(self) -> None:
        if MEMORY_PATH.exists():
            try:
                data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
                self._team = str(data.get("team", ""))
                self._agents = {k: list(v) for k, v in (data.get("agents") or {}).items()}
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self) -> None:
        MEMORY_PATH.parent.mkdir(exist_ok=True)
        MEMORY_PATH.write_text(
            json.dumps({"team": self._team, "agents": self._agents}, ensure_ascii=False, indent=2),
            encoding="utf-8")

    # --- team memory ---
    def team(self) -> str:
        return self._team

    def set_team(self, text: str) -> str:
        with self._lock:
            self._team = str(text or "").strip()
            self._save()
            return self._team

    # --- per-agent memory ---
    def agent_notes(self, agent_id: str) -> list[str]:
        return list(self._agents.get(agent_id, []))

    def add_agent_note(self, agent_id: str, note: str) -> None:
        note = str(note or "").strip()[:NOTE_MAX_CHARS]
        if not note:
            return
        with self._lock:
            notes = self._agents.setdefault(agent_id, [])
            notes.append(note)
            del notes[:-NOTES_PER_AGENT]   # เก็บแค่ N ล่าสุด
            self._save()

    def clear_agent(self, agent_id: str) -> None:
        with self._lock:
            self._agents.pop(agent_id, None)
            self._save()

    def context_block(self, agent_id: str) -> str:
        """ข้อความ memory สำหรับแปะใน system prompt (ว่าง = ไม่มีอะไรให้จำ)"""
        parts: list[str] = []
        if self._team:
            parts.append("ความจำร่วมของทีม:\n" + self._team)
        notes = self.agent_notes(agent_id)
        if notes:
            parts.append("งานที่คุณ (agent นี้) เคยทำล่าสุด:\n" + "\n".join(f"- {n}" for n in notes))
        return "\n\n".join(parts)


memory_service = MemoryService()
