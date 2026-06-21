"""M21-3 QA Gate — Task Continuation

offline: ตรวจ orchestration_store (M21-1), continue_run รันเฉพาะขั้นค้าง (M21-2),
run() เซฟ state + emit result, route wiring, error cases.
รัน: .venv\\Scripts\\python.exe daemon\\qa_m21.py
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daemon.models.schemas import AgentConfig, LLMConfig, TaskLog  # noqa: E402
from daemon.services import orchestration_store as OS  # noqa: E402
from daemon.services import orchestrator_service as O  # noqa: E402
from daemon.services import task_router as TR  # noqa: E402

_FAILS: list[str] = []


def check(name, cond):
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        _FAILS.append(name)


def _isolate_store() -> None:
    """ชี้ store ไปไฟล์ชั่วคราว — ไม่แตะ data จริง"""
    tmp = Path(tempfile.mkdtemp()) / "orch.json"
    OS.STORE = tmp
    OS.DATA_DIR = tmp.parent


def main() -> int:
    _isolate_store()
    store = OS.orchestration_store

    # 1) store round-trip + นับ pending/done + cap + latest/list
    store.save("t1", "สร้างเกม mario", [
        {"role": "designer", "subtask": "ออกแบบ GDD", "agent_id": "d",
         "agent_name": "ET Designer", "status": "done", "output": "ได้ GDD"},
        {"role": "coder", "subtask": "เขียนโค้ดเกม", "agent_id": "c",
         "agent_name": "ET Developer", "status": "failed", "output": "❌ พัง"},
    ])
    st = store.get("t1")
    check("store: get คืน state ที่บันทึก", st is not None and st["message"] == "สร้างเกม mario")
    check("store: นับ done/pending ถูก (1 done, 1 pending)", st["done"] == 1 and st["pending"] == 1)
    check("store: latest = ตัวล่าสุด", store.latest()["task_id"] == "t1")
    store.save("t2", "อีกงาน", [{"subtask": "x", "status": "done"}])
    lst = store.list()
    check("store: list ใหม่สุดก่อน + ไม่มี steps เต็ม", lst[0]["task_id"] == "t2" and "steps" not in lst[0])
    store.save("t1", "สร้างเกม mario", [{"subtask": "y", "status": "done"}])  # ทับ
    check("store: save ซ้ำ task_id เดิม = ทับ ไม่ซ้ำ", sum(1 for i in store._read() if i["task_id"] == "t1") == 1)

    # --- mocks ร่วม (เลียนแบบ qa_m20) ---
    _events: list[dict] = []
    O.ws_manager.broadcast_threadsafe = lambda loop, msg: _events.append(msg)
    O._workspace_files = lambda limit=40: []
    svc = O.orchestrator_service
    prod = AgentConfig(name="ET Producer", role="Producer",
                       llm=LLMConfig(provider="ollama", model="qwen3:8b"))
    O.registry._agents = {
        prod.id: prod,
        "d": AgentConfig(id="d", name="ET Designer", role="designer"),
        "c": AgentConfig(id="c", name="ET Developer", role="coder"),
    }

    calls: list[str] = []

    def fake_runsync(sub, agent, m):
        calls.append(agent.role)
        m["produced_kinds"] = ["code"] if agent.role == "coder" else ["file"]
        m["produced_output"] = True
        return "ทำเสร็จแล้วครับ"

    orig = TR.task_router.run_sync
    TR.task_router.run_sync = fake_runsync
    try:
        # 2) run() เซฟ state + emit orchestrate.result
        _events.clear()
        plan = [{"role": "designer", "subtask": "ออกแบบ GDD"},
                {"role": "coder", "subtask": "เขียนโค้ดเกม"}]
        svc._decompose = lambda *a, **k: plan
        rtask = TaskLog(message="สร้างเกม mario", agent_id=prod.id, agent_name=prod.name)
        svc._synthesize = lambda *a, **k: "สรุปงาน"   # ตัด LLM ออกจากเทส
        svc.run(rtask, prod, {}, loop=None)
        saved = store.get(rtask.task_id)
        check("run: เซฟ state 2 ขั้น", saved is not None and saved["total"] == 2)
        check("run: emit orchestrate.result", any(e["type"] == "orchestrate.result" for e in _events))

        # 3) continue_run รันเฉพาะขั้นค้าง (ข้าม done) + merge done เดิม
        calls.clear()
        _events.clear()
        store.save("cont1", "สร้างเกม mario", [
            {"role": "designer", "subtask": "ออกแบบ GDD", "agent_id": "d",
             "agent_name": "ET Designer", "status": "done", "output": "ได้ GDD แล้ว"},
            {"role": "coder", "subtask": "เขียนโค้ดเกม", "agent_id": "c",
             "agent_name": "ET Developer", "status": "failed", "output": "❌ พัง"},
        ])
        captured = {}
        svc._synthesize = lambda goal, results, *a, **k: captured.setdefault("results", results) or "สรุป"
        ctask = TaskLog(message="สร้างเกม mario", agent_id=prod.id, agent_name=prod.name)
        svc.continue_run(ctask, prod, "cont1", {}, loop=None)
        check("continue: รัน run_sync แค่ขั้นค้าง (coder) ไม่ทำ designer ซ้ำ", calls == ["coder"])
        res = captured.get("results", [])
        check("continue: synthesize เห็นครบ 2 ขั้น (done เดิม + ใหม่)", len(res) == 2)
        check("continue: ขั้น done เดิมถูกคงสถานะ done", any(r[3] == "done" and r[0].name == "ET Designer" for r in res))
        new_state = store.get(ctask.task_id)
        check("continue: state ใหม่ pending=0 (ครบแล้ว)", new_state and new_state["pending"] == 0)

        # 4) continue_run: ครบทุกขั้นแล้ว → ไม่รันอะไร
        calls.clear()
        store.save("alldone", "x", [{"subtask": "a", "status": "done"}])
        msg = svc.continue_run(TaskLog(message="x"), prod, "alldone", {}, loop=None)
        check("continue: ครบแล้ว → ไม่รัน + แจ้ง", calls == [] and "เสร็จ" in msg)
    finally:
        TR.task_router.run_sync = orig

    # 5) continue_orchestration error cases (async)
    async def _errs():
        miss = no_pending = False
        try:
            await TR.task_router.continue_orchestration("ไม่มีจริง")
        except KeyError:
            miss = True
        try:
            await TR.task_router.continue_orchestration("alldone")
        except ValueError:
            no_pending = True
        return miss, no_pending

    miss, no_pending = asyncio.run(_errs())
    check("continue_orchestration: ไม่มี state → KeyError (404)", miss)
    check("continue_orchestration: ครบทุกขั้น → ValueError (409)", no_pending)

    # 6) route wiring
    from daemon.routes import tasks as tasks_route
    paths = {r.path for r in tasks_route.router.routes}
    check("route: POST /tasks/{task_id}/continue ลงทะเบียน", "/tasks/{task_id}/continue" in paths)
    check("route: GET /tasks/{task_id}/state ลงทะเบียน", "/tasks/{task_id}/state" in paths)
    check("route: GET /orchestrations ลงทะเบียน", "/orchestrations" in paths)

    print()
    if _FAILS:
        print(f"M21-3 QA: {len(_FAILS)} FAILED -> {_FAILS}")
        return 1
    print("M21-3 QA: ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
