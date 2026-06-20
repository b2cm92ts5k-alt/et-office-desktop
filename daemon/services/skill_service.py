"""SkillService (M15-1) — สูตรทำงานทีละขั้น (markdown) inject เข้า prompt ของ sub-agent

skill = ไฟล์ .md (YAML frontmatter + body) คล้าย role:
    ---
    name: research-and-report
    description: ใช้เมื่อต้องค้นข้อมูลแล้วสรุปเป็นรายงาน/เอกสาร
    when: [ค้นหา, วิจัย, สรุป, รายงาน, research]
    tools: [web_search, fetch_url, write_file]
    ---
    (เนื้อหา = ขั้นตอนการทำงาน อ้าง tool จริงของ ET Office)

match แบบ keyword (D5 — ถูก/เร็ว/เสถียร): นับ `when` keyword + คำใน description ที่โผล่ใน
(task message + role) → เลือก skill คะแนนสูงสุด (สูงสุด `MAX_INJECT` ตัว). ไม่ match = ไม่ inject
(ไม่รบกวนงานง่าย). disabled_skills ใน settings → ข้าม (ให้ UI M15-3 เปิด/ปิดได้).

inject เข้า system prompt ใน `_run_tool_loop` — clip ตาม budget กัน context ล้น (M11-6).
preset skills อยู่ใน repo (daemon/skills); skill ที่ user สร้างเองอยู่ data/skills (นอก git).
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

SKILLS_DIR = Path(__file__).parent.parent / "skills"               # preset (ใน git)
USER_SKILLS_DIR = Path(__file__).parent.parent / "data" / "skills"  # user (นอก git)

MAX_INJECT = 1        # inject กี่ skill ต่อ task (เริ่ม 1 กัน context ล้น)
MAX_SKILL_CHARS = 1600  # clip body กัน sys prompt บาน (≈400 tok)


def _as_list(raw) -> list[str]:
    if isinstance(raw, str):
        return [k.strip() for k in re.split(r"[,，]|\s{2,}", raw) if k.strip()]
    return [str(k).strip() for k in (raw or []) if str(k).strip()]


def parse_skill_md(text: str, filename: str = "") -> dict:
    name = Path(filename).stem if filename else "skill"
    meta: dict = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            meta = yaml.safe_load(parts[1]) or {}
            body = parts[2].strip()
    return {
        "name": str(meta.get("name", name)),
        "description": str(meta.get("description", "")),
        "when": _as_list(meta.get("when")),
        "tools": _as_list(meta.get("tools")),
        "body": body,
        "file": filename,
    }


class SkillStore:
    def __init__(self) -> None:
        self._skills: list[dict] = []
        self.reload()

    def reload(self) -> None:
        out: list[dict] = []
        for d in (SKILLS_DIR, USER_SKILLS_DIR):
            if d.exists():
                for f in sorted(d.glob("*.md")):
                    try:
                        out.append(parse_skill_md(f.read_text(encoding="utf-8"), f.name))
                    except (OSError, yaml.YAMLError):
                        continue
        self._skills = out

    def all(self) -> list[dict]:
        return self._skills

    def public_list(self) -> list[dict]:
        """รายการ skill สำหรับ UI (M15-3) — มี enabled + builtin (preset แก้ไม่ได้)"""
        disabled = self._disabled()
        builtin = {f.stem for f in SKILLS_DIR.glob("*.md")} if SKILLS_DIR.exists() else set()
        return [{"name": s["name"], "description": s["description"], "when": s["when"],
                 "tools": s["tools"], "body": s["body"],
                 "enabled": s["name"] not in disabled,
                 "builtin": Path(s["file"]).stem in builtin} for s in self._skills]

    def set_enabled(self, name: str, enabled: bool) -> bool:
        """เปิด/ปิด skill (M15-3) — เก็บใน settings disabled_skills"""
        from .settings_store import settings_store
        disabled = set(settings_store.get("disabled_skills") or [])
        if enabled:
            disabled.discard(name)
        else:
            disabled.add(name)
        settings_store.update({"disabled_skills": sorted(disabled)})
        return name not in disabled

    def _disabled(self) -> set[str]:
        from .settings_store import settings_store
        return set(settings_store.get("disabled_skills") or [])

    def _score(self, skill: dict, hay: str) -> int:
        """นับ keyword (when) + คำใน description ที่โผล่ใน hay (task+role) — มากกว่า = ตรงกว่า"""
        score = 0
        for kw in skill["when"]:
            if kw and kw.lower() in hay:
                score += 2   # when keyword = สัญญาณแรง
        for word in re.findall(r"[a-zA-Z฀-๿]{3,}", skill["description"].lower()):
            if word in hay:
                score += 1
        return score

    def match(self, message: str, role: str = "", limit: int = MAX_INJECT) -> list[dict]:
        hay = f"{message} {role}".lower()
        disabled = self._disabled()
        scored = [(self._score(s, hay), s) for s in self._skills if s["name"] not in disabled]
        scored = [(sc, s) for sc, s in scored if sc > 0]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:limit]]

    def context_block(self, message: str, role: str = "") -> str:
        """ข้อความ skill ที่ match — เอาไป append เข้า system prompt (ว่าง = ไม่มี match)"""
        skills = self.match(message, role)
        if not skills:
            return ""
        parts = []
        for s in skills:
            body = s["body"]
            if len(body) > MAX_SKILL_CHARS:
                body = body[:MAX_SKILL_CHARS] + "\n…(ตัดเพื่อประหยัด context)"
            parts.append(f"📋 สกิลที่เกี่ยวข้อง — {s['name']}: {s['description']}\n{body}")
        return "‼️ ทำตามสูตรสกิลนี้:\n\n" + "\n\n".join(parts)


skill_service = SkillStore()
