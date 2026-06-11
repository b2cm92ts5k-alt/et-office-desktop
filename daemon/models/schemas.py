"""Pydantic schemas — ทุก data shape ที่วิ่งผ่าน API และ WebSocket (M1-2)"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

AgentStatus = Literal["idle", "working", "thinking", "collab", "break", "sleep"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid4().hex[:12]


class LLMConfig(BaseModel):
    """ค่า model ของ agent — local (ollama) หรือ cloud (claude/gemini/openai)"""
    provider: Literal["ollama", "claude", "gemini", "openai"] = "ollama"
    model: str = "qwen3:8b"


class AgentConfig(BaseModel):
    id: str = Field(default_factory=_new_id)
    name: str
    role: str
    avatar: str = "🤖"
    color: str = "#00e5ff"          # neon aura color ตาม role
    keywords: list[str] = []
    system_prompt: str = ""
    backstory: str = ""
    llm: LLMConfig = LLMConfig()
    status: AgentStatus = "idle"


class AgentCreate(BaseModel):
    name: str
    role: str
    avatar: str = "🤖"
    color: str = "#00e5ff"
    keywords: list[str] = []
    system_prompt: str = ""
    backstory: str = ""
    llm: LLMConfig = LLMConfig()


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    avatar: Optional[str] = None
    color: Optional[str] = None
    keywords: Optional[list[str]] = None
    system_prompt: Optional[str] = None
    backstory: Optional[str] = None
    llm: Optional[LLMConfig] = None


class TaskRequest(BaseModel):
    message: str


class TaskLog(BaseModel):
    task_id: str = Field(default_factory=_new_id)
    message: str
    agent_id: str = ""
    agent_name: str = ""
    status: Literal["routing", "working", "completed", "failed"] = "routing"
    output: str = ""
    created_at: str = Field(default_factory=_now)
    finished_at: str = ""


class Proposal(BaseModel):
    id: str = Field(default_factory=_new_id)
    title: str
    detail: str = ""
    proposed_by: list[str] = []      # agent ids
    status: Literal["pending", "approved", "rejected"] = "pending"
    note: str = ""
    created_at: str = Field(default_factory=_now)


class LogEntry(BaseModel):
    id: int = 0
    ts: str = Field(default_factory=_now)
    agent_id: str = ""
    type: str = "info"               # info / task / status / social / error
    message: str = ""


class OEPEvent(BaseModel):
    """Office Event Protocol — ทุก event ที่ broadcast ผ่าน WebSocket hub"""
    type: str
    ts: str = Field(default_factory=_now)
    data: dict[str, Any] = {}


class ApiKeyRequest(BaseModel):
    provider: Literal["claude", "gemini", "openai"]
    key: str


class RolePreset(BaseModel):
    file: str
    name: str
    role: str
    avatar: str = "🤖"
    color: str = "#00e5ff"
    keywords: list[str] = []
    system_prompt: str = ""
