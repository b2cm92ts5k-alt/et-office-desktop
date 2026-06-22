"""M22-5 QA Gate — Agent Liveliness (chat++ ฝั่ง BE ที่ test ได้ offline)

ตรวจ: personality preset ต่อ role (M22-3), topic rotation, group constants, schema field.
ส่วน Godot (bubble/emote/idle/ambient) parse-check แยกด้วย godot --check-only;
จูนความถี่/GPU ต้องวัดในแอปจริง (manual).
รัน: .venv\\Scripts\\python.exe daemon\\qa_m22.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daemon.models.schemas import AgentConfig  # noqa: E402
from daemon.services import social_service as S  # noqa: E402

_FAILS: list[str] = []


def check(name, cond):
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        _FAILS.append(name)


def main() -> int:
    po = S.personality_of
    # 1) personality preset ตาม role (M22-3)
    check("persona: Game Developer → สาย coder/ตรรกะ",
          "ตรรกะ" in po(AgentConfig(name="Dev", role="Game Developer")))
    check("persona: Game Designer → สายขี้เล่น/จินตนาการ",
          "จินตนาการ" in po(AgentConfig(name="Dsg", role="Game Designer")))
    check("persona: Sound Designer → สายเสียง/จังหวะ",
          "จังหวะ" in po(AgentConfig(name="Snd", role="Sound Designer")))
    check("persona: QA Tester → สายละเอียด/จับผิด",
          "จับผิด" in po(AgentConfig(name="QA", role="QA & Tester")))
    check("persona: Producer → สายจัดระเบียบ",
          "จัดระเบียบ" in po(AgentConfig(name="Prod", role="Producer / Project Manager")))
    check("persona: role แปลก → default เป็นกันเอง",
          "เป็นกันเอง" in po(AgentConfig(name="X", role="นักบินอวกาศ")))
    # 2) personality ที่ตั้งเอง ชนะ preset (M22-3, §5: role .md กำหนดเองได้)
    custom = AgentConfig(name="C", role="Game Developer", personality="พูดน้อย เย็นชา ลึกลับ")
    check("persona: ตั้งเอง override preset", po(custom) == "พูดน้อย เย็นชา ลึกลับ")
    # keyword match จาก keywords ด้วย (ไม่ใช่แค่ role)
    check("persona: match จาก keywords",
          "เสียง" in po(AgentConfig(name="K", role="Specialist", keywords=["ดนตรี", "audio"])))

    # 3) topics + group constants
    check("topics: มีหลายหัวข้อหมุนเวียน (≥5)", len(S.TOPICS) >= 5)
    check("topics: ทุกหัวข้อเป็น str ไม่ว่าง", all(isinstance(t, str) and t for t in S.TOPICS))
    check("group: GROUP_MAX = 4 (วงคุยสูงสุด 3-4)", S.GROUP_MAX == 4)
    check("group: GROUP_CHANCE อยู่ใน (0,1)", 0 < S.GROUP_CHANCE < 1)
    check("group: TURN_GAP_SEC > 0 (สลับจังหวะ bubble)", S.TURN_GAP_SEC > 0)

    # 4) schema field personality (settable + persist)
    check("schema: AgentConfig.personality มี default ''", AgentConfig(name="a", role="b").personality == "")
    from daemon.models.schemas import AgentUpdate
    check("schema: AgentUpdate.personality optional", "personality" in AgentUpdate.model_fields)

    # 5) _run_crew/_run_chat รับ group (list) — signature เปลี่ยนเป็นวง
    import inspect
    sig = inspect.signature(S.social_service._run_crew)
    check("_run_crew(group, topic) — รองรับวงคุย", "group" in sig.parameters and "topic" in sig.parameters)

    print()
    if _FAILS:
        print(f"M22-5 QA: {len(_FAILS)} FAILED -> {_FAILS}")
        return 1
    print("M22-5 QA: ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
