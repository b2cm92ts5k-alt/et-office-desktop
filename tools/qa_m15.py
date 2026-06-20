"""QA Gate M15 — Real Teamwork & Skills (เริ่ม M15-1/M15-2 skills; จะเพิ่ม orchestrator/web_search)

รัน: python tools/qa_m15.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_results: list[tuple[bool, str]] = []


def check(name: str, ok: bool, info: str = "") -> None:
    _results.append((bool(ok), name))
    print(("PASS" if ok else "FAIL"), "-", name, (f"  [{info}]" if info else ""))


def main() -> None:
    from daemon.services.skill_service import skill_service as S

    print("--- M15-1/2 Skills ---")
    names = {s["name"] for s in S.all()}
    expected = {"research-and-report", "build-feature", "write-plan", "organize-files", "small-game-team"}
    check("โหลด skill ชุดแรกครบ 5", expected <= names, ",".join(sorted(names)))
    check("ทุก skill มี description + when", all(s["description"] and s["when"] for s in S.all()))

    # match ถูกตัว
    cases = {
        "ค้นข้อมูลคู่แข่งแล้วทำรายงาน": "research-and-report",
        "เขียนฟังก์ชัน login เป็นโค้ด": "build-feature",
        "วางแผน roadmap sprint หน้า": "write-plan",
        "จัดระเบียบไฟล์ใน workspace": "organize-files",
        "ทำ prototype เกม platformer": "small-game-team",
    }
    for msg, want in cases.items():
        got = [s["name"] for s in S.match(msg)]
        check(f"match: {msg[:24]} → {want}", got[:1] == [want], ",".join(got) or "ว่าง")

    # ไม่ match งานทั่วไป (ไม่ spam)
    check("งานทั่วไปไม่ match (ไม่ inject มั่ว)", S.match("สวัสดีครับ วันนี้เป็นไงบ้าง") == [])
    check("context_block ว่างเมื่อไม่ match", S.context_block("สวัสดี") == "")
    blk = S.context_block("ทำเกม platformer", "game-programmer")
    check("context_block มีเนื้อ skill เมื่อ match", "สกิลที่เกี่ยวข้อง" in blk and len(blk) < 2000)

    # integrate เข้า task_router
    import inspect
    from daemon.services.task_router import TaskRouter
    src = inspect.getsource(TaskRouter._run_tool_loop)
    check("inject skill ใน _run_tool_loop", "skill_service.context_block" in src)

    passed = sum(1 for ok, _ in _results if ok)
    total = len(_results)
    print(f"\n===== M15 QA: {passed}/{total} PASS =====")
    if passed != total:
        print("FAILED:", [n for ok, n in _results if not ok])
        sys.exit(1)


if __name__ == "__main__":
    main()
