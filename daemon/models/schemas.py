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


CloudProvider = Literal["claude", "gemini", "openai", "grok", "deepseek"]


class LLMConfig(BaseModel):
    """ค่า model ของ agent — local (ollama) หรือ cloud (claude/gemini/openai/grok/deepseek)

    cloud เลือก credential ได้ 2 ทาง (M14-4): `account_id` (ProviderAccount api_key เข้ารหัส DPAPI)
    มาก่อน ถ้าว่างจึง fallback `key_id` (M11-14 เดิม) แล้วค่อย default .env — backward compat.
    เก็บแค่ id อ้างอิง ไม่เคยเก็บ secret.
    """
    provider: Literal["ollama", "claude", "gemini", "openai", "grok", "deepseek"] = "ollama"
    model: str = "qwen3:8b"
    account_id: str = ""   # M14-4 — ProviderAccount (ใหม่)
    key_id: str = ""       # M11-14 — multi-key เดิม (คงไว้ compat)


class AgentConfig(BaseModel):
    id: str = Field(default_factory=_new_id)
    name: str
    role: str
    avatar: str = "🤖"
    color: str = "#00e5ff"          # neon aura color ตาม role
    keywords: list[str] = []
    system_prompt: str = ""
    backstory: str = ""
    sprite: str = ""                # custom spritesheet ใน data/sprites/ (M6-2 v2)
    is_ceo: bool = False            # ตัวละคร CEO/ผู้ใช้ จาก onboarding (M8) — ไล่ออกไม่ได้
    llm: LLMConfig = LLMConfig()
    allowed_tools: list[str] = []   # M11-3 whitelist ต่อ role — ว่าง = อนุญาตทุก tool (backward compat)
    thinking_mode: bool = False     # M11-8 — True = /think (วางแผน, orchestrator); False = /no_think (worker, เร็ว 2-3x)
    key_id: str = ""                # M11-14 — เลือก cloud key อันไหน (ว่าง = default จาก .env); ไม่เก็บ secret
    status: AgentStatus = "idle"


class AgentCreate(BaseModel):
    name: str
    role: str
    avatar: str = "🤖"
    color: str = "#00e5ff"
    keywords: list[str] = []
    system_prompt: str = ""
    backstory: str = ""
    sprite: str = ""
    is_ceo: bool = False
    llm: LLMConfig = LLMConfig()
    allowed_tools: list[str] = []   # M11-3
    thinking_mode: bool = False     # M11-8
    key_id: str = ""                # M11-14


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    avatar: Optional[str] = None
    color: Optional[str] = None
    keywords: Optional[list[str]] = None
    system_prompt: Optional[str] = None
    backstory: Optional[str] = None
    sprite: Optional[str] = None
    llm: Optional[LLMConfig] = None
    allowed_tools: Optional[list[str]] = None   # M11-3
    thinking_mode: Optional[bool] = None        # M11-8
    key_id: Optional[str] = None                # M11-14


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


class ProposalCreate(BaseModel):
    title: str
    detail: str = ""
    proposed_by: list[str] = []


class ProposalRespond(BaseModel):
    proposal_id: str
    action: Literal["approve", "reject"]
    note: str = ""


class SocialSettings(BaseModel):
    """ปรับ social loop runtime — field ไหนไม่ส่ง = คงค่าเดิม"""
    social_enabled: Optional[bool] = None
    social_interval_sec: Optional[float] = Field(default=None, ge=5)
    social_chance: Optional[float] = Field(default=None, ge=0, le=1)
    proposal_cooldown_sec: Optional[float] = Field(default=None, ge=0)


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
    provider: Literal["claude", "gemini", "openai", "grok", "deepseek"]
    key: str


class RolePreset(BaseModel):
    file: str
    name: str
    role: str
    avatar: str = "🤖"
    color: str = "#00e5ff"
    keywords: list[str] = []
    system_prompt: str = ""


class PermissionRespond(BaseModel):
    """M6-8 — คำตอบของผู้ใช้ต่อคำขอ action"""
    request_id: str
    decision: Literal["approve", "deny", "approve_task"]


class WorkspaceSettings(BaseModel):
    """M6-6 — โฟลเดอร์ workspace ของทีม ("" = ปิด tool use)"""
    path: str = ""


class RoleDraftRequest(BaseModel):
    """M6-3 — ให้ AI ร่างไฟล์ role .md จากคำอธิบายสั้น ๆ"""
    description: str


class RoleSaveRequest(BaseModel):
    """M6-2 — บันทึก role .md ลง daemon/roles/ ให้ใช้ซ้ำได้"""
    filename: str = ""
    text: str
