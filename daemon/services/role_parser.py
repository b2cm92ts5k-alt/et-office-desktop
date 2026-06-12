"""RoleParser — parse .md (YAML frontmatter + body) → RolePreset (M1-10)

รูปแบบไฟล์ role:
    ---
    name: ET Producer
    role: Producer / Project Manager
    avatar: "💜"
    color: "#e040fb"
    keywords: [แผน, plan, roadmap, จัดการ]
    ---
    (เนื้อหา markdown ต่อจากนี้ = system prompt)
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from ..models.schemas import RolePreset

ROLES_DIR = Path(__file__).parent.parent / "roles"


def _as_keyword_list(raw) -> list[str]:
    """ทน format เพี้ยนจาก LLM/มือคน — list ปกติ, string คั่น comma, หรือคั่น space"""
    if isinstance(raw, str):
        sep = "," if ("," in raw or "，" in raw) else None
        return [k.strip() for k in re.split(r"[,，]" if sep else r"\s+", raw) if k.strip()]
    return [str(k).strip() for k in (raw or []) if str(k).strip()]


def parse_role_md(text: str, filename: str = "") -> RolePreset:
    name = Path(filename).stem if filename else "agent"
    meta: dict = {}
    body = text

    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            meta = yaml.safe_load(parts[1]) or {}
            body = parts[2].strip()

    return RolePreset(
        file=filename,
        name=str(meta.get("name", name)),
        role=str(meta.get("role", name)),
        avatar=str(meta.get("avatar", "🤖")),
        color=str(meta.get("color", "#00e5ff")),
        keywords=_as_keyword_list(meta.get("keywords")),
        system_prompt=body,
    )


def load_preset_roles() -> list[RolePreset]:
    presets = []
    if ROLES_DIR.exists():
        for f in sorted(ROLES_DIR.glob("*.md")):
            presets.append(parse_role_md(f.read_text(encoding="utf-8"), f.name))
    return presets
