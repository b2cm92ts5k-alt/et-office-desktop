"""AgentRegistry — CRUD + state เก็บเป็น JSON file ตาม blueprint (M1-6)
seed อัตโนมัติจาก preset roles ถ้า registry ยังว่าง
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

from ..models.schemas import AgentConfig, AgentCreate, AgentUpdate
from .role_parser import load_preset_roles

REGISTRY_PATH = Path(__file__).parent.parent / "data" / "agents.json"


class AgentRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._agents: dict[str, AgentConfig] = {}
        REGISTRY_PATH.parent.mkdir(exist_ok=True)
        self._load()

    # --- persistence ---

    def _load(self) -> None:
        if REGISTRY_PATH.exists():
            raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
            self._agents = {a["id"]: AgentConfig(**a) for a in raw}
        if not self._agents:
            self._seed_from_presets()

    def _save(self) -> None:
        data = [a.model_dump() for a in self._agents.values()]
        REGISTRY_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _seed_from_presets(self) -> None:
        """สร้างทีมเริ่มต้นจาก daemon/roles/*.md"""
        for preset in load_preset_roles():
            agent = AgentConfig(
                name=preset.name,
                role=preset.role,
                avatar=preset.avatar,
                color=preset.color,
                keywords=preset.keywords,
                system_prompt=preset.system_prompt,
            )
            self._agents[agent.id] = agent
        if self._agents:
            self._save()

    # --- CRUD ---

    def all(self) -> list[AgentConfig]:
        return list(self._agents.values())

    def get(self, agent_id: str) -> Optional[AgentConfig]:
        return self._agents.get(agent_id)

    def create(self, payload: AgentCreate) -> AgentConfig:
        with self._lock:
            agent = AgentConfig(**payload.model_dump())
            self._agents[agent.id] = agent
            self._save()
            return agent

    def update(self, agent_id: str, payload: AgentUpdate) -> Optional[AgentConfig]:
        with self._lock:
            agent = self._agents.get(agent_id)
            if not agent:
                return None
            changes = {k: v for k, v in payload.model_dump().items() if v is not None}
            updated = agent.model_copy(update=changes)
            self._agents[agent_id] = updated
            self._save()
            return updated

    def delete(self, agent_id: str) -> bool:
        with self._lock:
            if agent_id not in self._agents:
                return False
            del self._agents[agent_id]
            self._save()
            return True

    def set_status(self, agent_id: str, status: str) -> None:
        agent = self._agents.get(agent_id)
        if agent:
            agent.status = status  # in-memory เท่านั้น ไม่ persist ทุกครั้ง


registry = AgentRegistry()
