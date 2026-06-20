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

    print("--- M15-3 Skills UI/route ---")
    from daemon.services.settings_store import settings_store
    settings_store.update({"disabled_skills": []})
    pub = S.public_list()
    check("public_list มี enabled/builtin/body", all({"enabled", "builtin", "body"} <= set(p) for p in pub))
    check("skill ทั้งหมด builtin (preset)", all(p["builtin"] for p in pub))
    S.set_enabled("build-feature", False)
    check("set_enabled ปิด → persist ใน settings", "build-feature" in (settings_store.get("disabled_skills") or []))
    check("skill ที่ปิด ถูกข้ามใน match", "build-feature" not in [s["name"] for s in S.match("เขียนโค้ด")])
    S.set_enabled("build-feature", True)
    check("set_enabled เปิดคืน", "build-feature" not in (settings_store.get("disabled_skills") or []))
    from fastapi.testclient import TestClient
    from daemon.main import app
    _c = TestClient(app)
    check("GET /skills 200 + 5 skill", _c.get("/skills").status_code == 200 and len(_c.get("/skills").json()["skills"]) == 5)
    check("PUT /skills/{name} toggle", _c.put("/skills/write-plan", json={"enabled": False}).json()["enabled"] is False)
    _c.put("/skills/write-plan", json={"enabled": True})

    print("--- M15-4 web_search tool ---")
    from daemon.services import tool_executor as TE
    check("web_search ใน TOOLS_SPEC", "web_search" in TE.TOOLS_SPEC)
    check("web_search อยู่ใน preset researcher", "web_search" in TE.ROLE_TOOL_PRESETS["researcher"])
    check("มี _web_search (keyless DDG + optional Brave)", hasattr(TE, "_web_search"))
    check("query ว่าง → ขอ query (ไม่ throw)", TE._web_search("") == "ต้องมี query")

    print("--- M15-5 Orchestrator (Sub-Agent) ---")
    import json as _json
    from daemon.services import orchestrator_service as OM
    from daemon.services.agent_registry import registry
    from daemon.services import task_router as TRmod
    from daemon.services import ws_manager as WS
    from daemon.adapters import llm_adapter as LA
    from daemon.models.schemas import AgentConfig, TaskLog, LLMConfig

    check("orchestrator_service + PLAN_SCHEMA", hasattr(OM, "orchestrator_service") and "plan" in OM.PLAN_SCHEMA["properties"])
    rsrc = inspect.getsource(TaskRouter.route_and_execute)
    check("route_and_execute: ไม่มี target → orchestrate", "orchestrate = True" in rsrc and "_default_agent" in rsrc)
    esrc = inspect.getsource(TaskRouter._execute)
    check("_execute เรียก orchestrator เมื่อ orchestrate", "orchestrator_service.run" in esrc)

    # flow ด้วย stub (decompose 2 งาน → dispatch → synthesize)
    prod = AgentConfig(name="Pro", role="Producer", is_ceo=False, llm=LLMConfig(provider="ollama"))
    res = AgentConfig(name="Rey", role="Researcher", keywords=["วิจัย"], is_ceo=False)
    prog = AgentConfig(name="Cody", role="Programmer", keywords=["code"], is_ceo=False)
    registry._agents = {a.id: a for a in [prod, res, prog]}
    check("_pick_agent ตาม role", OM.orchestrator_service._pick_agent("Researcher", "x").name == "Rey")
    LA.ollama_chat = lambda messages, schema=None, **kw: (
        _json.dumps({"plan": [{"role": "Researcher", "subtask": "ค้น X"},
                              {"role": "Programmer", "subtask": "เขียน Y"}]}) if schema else "สรุปงานเสร็จ")
    dispatched = []
    TRmod.task_router.run_sync = lambda sub, agent, m=None: dispatched.append(agent.name) or f"done {sub.message}"
    WS.ws_manager.broadcast_threadsafe = lambda loop, ev: None
    out = OM.orchestrator_service.run(TaskLog(message="ทำ X", agent_id=prod.id, agent_name="Pro"), prod, {}, None)
    check("orchestrate dispatch 2 agent ถูกตัว", dispatched == ["Rey", "Cody"], ",".join(dispatched))
    check("synthesize คืนผลรวม", out == "สรุปงานเสร็จ")

    passed = sum(1 for ok, _ in _results if ok)
    total = len(_results)
    print(f"\n===== M15 QA: {passed}/{total} PASS =====")
    if passed != total:
        print("FAILED:", [n for ok, n in _results if not ok])
        sys.exit(1)


if __name__ == "__main__":
    main()
