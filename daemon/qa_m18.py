"""M18-4 QA Gate — Role Tool Presets

offline: เรียก matcher + endpoint handler ตรง ๆ. ตรวจ role free-text → preset ถูกตัว,
ลำดับ sound/game designer, role แปลก → None, endpoint คืน presets+match.
รัน: .venv\\Scripts\\python.exe daemon\\qa_m18.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daemon.routes.system import tool_presets  # noqa: E402
from daemon.services.tool_executor import ROLE_TOOL_PRESETS, preset_for_role  # noqa: E402

_FAILS: list[str] = []


def check(name: str, cond: bool) -> None:
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        _FAILS.append(name)


def main() -> int:
    # 1) matcher ต่อ role จริงของทีม
    cases = {
        "Sound Designer": "sound", "Game Designer": "designer", "ET Developer": "coder",
        "Game Developer": "coder", "ET Artist": "artist", "QA & Tester": "tester",
        "Researcher": "researcher", "Producer/Project Manager": "producer",
        "Narrative Writer": "writer", "UX/UI Designer": "designer",
    }
    for role, exp in cases.items():
        m = preset_for_role(role)
        check(f"role '{role}' → {exp}", bool(m) and m["preset"] == exp)

    # 2) ลำดับ keyword (sound ต้องชนะ designer ใน 'Sound Designer')
    check("ลำดับ: Sound Designer ≠ designer", preset_for_role("Sound Designer")["preset"] == "sound")

    # 3) match จาก keywords ด้วย (ไม่ใช่แค่ role)
    m = preset_for_role("ผู้ช่วย", ["วาดรูป", "ภาพ"])
    check("match จาก keywords (วาดรูป → artist)", bool(m) and m["preset"] == "artist")

    # 4) role แปลก → None (ไม่ crash, ไม่ติ๊กอะไร = ทุก tool default)
    check("role ไม่ match → None", preset_for_role("นักบินอวกาศ") is None)

    # 5) tools ของ preset = สำเนา (แก้ไม่กระทบต้นฉบับ)
    m = preset_for_role("coder")
    m["tools"].append("HACK")
    check("preset_for_role คืนสำเนา (ไม่เปลี่ยนต้นฉบับ)", "HACK" not in ROLE_TOOL_PRESETS["coder"])

    # 6) endpoint
    r = tool_presets(role="Sound Designer")
    check("endpoint: match ถูก + presets ครบ", r["match"]["preset"] == "sound" and "artist" in r["presets"])
    r2 = tool_presets()
    check("endpoint: ไม่ส่ง role → match None + presets ครบ", r2["match"] is None and len(r2["presets"]) >= 8)

    # 7) artist preset มี generate_image (เชื่อม M17)
    check("artist preset → generate_image", "generate_image" in ROLE_TOOL_PRESETS["artist"])

    print()
    if _FAILS:
        print(f"M18-4 QA: {len(_FAILS)} FAILED -> {_FAILS}")
        return 1
    print("M18-4 QA: ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
