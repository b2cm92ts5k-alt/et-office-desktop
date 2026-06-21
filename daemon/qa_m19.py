"""M19-5 QA Gate — Orchestration Reliability

offline: mock LLM (ollama_chat) + execute + permission เพื่อขับ tool-loop/orchestrator จริง.
ตรวจ: REJECT→ล้มจริง(ไม่ retry/ไม่หลอกเสร็จ) · anti tool-spam ตัดวง · produced_output ·
orchestrator skip ขั้นที่เหลือเมื่อ reject + honest synthesize header.
รัน: .venv\\Scripts\\python.exe daemon\\qa_m19.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daemon.models.schemas import AgentConfig, LLMConfig, TaskLog  # noqa: E402
from daemon.services import orchestrator_service as O  # noqa: E402
from daemon.services import task_router as TR  # noqa: E402
from daemon.services.settings_store import settings_store  # noqa: E402

_FAILS: list[str] = []


def check(name, cond):
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        _FAILS.append(name)


def _seq(actions):
    """คืน callable ที่ป้อน action JSON ทีละตัว (ตัวสุดท้ายวนซ้ำ) ให้ ollama_chat mock"""
    box = {"i": 0}
    def fn(messages, **kw):
        i = min(box["i"], len(actions) - 1)
        box["i"] += 1
        return actions[i]
    return fn, box


def main() -> int:
    tmp = tempfile.mkdtemp()
    old_ws = settings_store.get("workspace_path")
    settings_store.update({"workspace_path": tmp})
    A = AgentConfig(name="W", role="worker", llm=LLMConfig(provider="ollama", model="qwen3:8b"))
    orig_exec, orig_perm, orig_chat = TR.execute, TR.permission_gate.request, TR.ollama_chat
    try:
        # 1) REJECT → _Rejected (ไม่ retry, ไม่ปั้น final)
        TR.permission_gate.request = lambda *a, **k: False
        TR.execute = lambda *a, **k: "ok"
        fn, _ = _seq(['{"action":{"tool":"write_file","args":{"path":"a.txt","content":"hi"}}}'])
        TR.ollama_chat = fn
        rej = False
        try:
            TR.task_router._run_tool_loop(TaskLog(message="ทำงาน", agent_id=A.id, agent_name=A.name), A)
        except TR._Rejected:
            rej = True
        check("REJECT → raise _Rejected (ไม่ปั้น final)", rej)

        # 2) _run_tool_loop_retry ไม่ retry _Rejected
        calls = {"n": 0}
        def chat_count(m, **k):
            calls["n"] += 1
            return '{"action":{"tool":"write_file","args":{"path":"a.txt","content":"x"}}}'
        TR.ollama_chat = chat_count
        try:
            TR.task_router._run_tool_loop_retry(TaskLog(message="x", agent_id=A.id, agent_name=A.name), A)
        except TR._Rejected:
            pass
        check("reject ไม่ retry (เรียก LLM ครั้งเดียว)", calls["n"] == 1)

        # 3) anti tool-spam: เรียก tool เดิมซ้ำ → ตัดวง (ไม่วนจน MAX_STEPS)
        TR.permission_gate.request = lambda *a, **k: True
        TR.execute = lambda *a, **k: "ผลเหมือนเดิม"
        spam = {"n": 0}
        def chat_spam(m, **k):
            spam["n"] += 1
            return '{"action":{"tool":"web_search","args":{"query":"same"}}}'
        TR.ollama_chat = chat_spam
        broke = False
        try:
            TR.task_router._run_tool_loop(TaskLog(message="หา", agent_id=A.id, agent_name=A.name), A)
        except TR._AttemptFailed:
            broke = True
        check("anti-spam: tool ซ้ำ → _AttemptFailed (ตัดวง)", broke)
        check("anti-spam: ตัดที่ ~5 ครั้ง (ไม่วนจน MAX_STEPS=10)", spam["n"] <= TR.SPAM_FAIL_AT + 1)

        # 4) produced_output flag: write_file สำเร็จ → True ; final อย่างเดียว → False
        TR.execute = lambda *a, **k: "เขียนแล้ว"
        fn, _ = _seq(['{"action":{"tool":"write_file","args":{"path":"b.txt","content":"c"}}}',
                      '{"final":"เสร็จแล้ว"}'])
        TR.ollama_chat = fn
        m1: dict = {}
        TR.task_router._run_tool_loop(TaskLog(message="เขียนไฟล์ b", agent_id=A.id, agent_name=A.name), A, metrics=m1)
        check("produced_output=True เมื่อมี write_file", m1.get("produced_output") is True)
        fn, _ = _seq(['{"final":"คุยเฉย ๆ"}', '{"final":"คุยเฉย ๆ"}'])  # pushback แล้วยืนยัน
        TR.ollama_chat = fn
        m2: dict = {}
        TR.task_router._run_tool_loop(TaskLog(message="คุย", agent_id=A.id, agent_name=A.name), A, metrics=m2)
        check("produced_output=False เมื่อไม่มี action", m2.get("produced_output") is False)
    finally:
        TR.execute, TR.permission_gate.request, TR.ollama_chat = orig_exec, orig_perm, orig_chat
        settings_store.update({"workspace_path": old_ws or ""})

    # 5) orchestrator: reject subtask 1 → skip ที่เหลือ + honest header (mock run_sync)
    svc = O.orchestrator_service
    plan = [{"role": "designer", "subtask": "ออกแบบ"}, {"role": "coder", "subtask": "เขียนโค้ดเกม"},
            {"role": "tester", "subtask": "ทดสอบ"}]
    svc._decompose = lambda *a, **k: plan
    O.ws_manager.broadcast_threadsafe = lambda *a, **k: None   # mock WS (ไม่มี loop ในเทส)
    prod = AgentConfig(name="ET Producer", role="Producer", llm=LLMConfig(provider="ollama", model="qwen3:8b"))
    O.registry._agents = {prod.id: prod,
                          "d": AgentConfig(name="ET Designer", role="designer"),
                          "c": AgentConfig(name="ET Developer", role="coder"),
                          "t": AgentConfig(name="ET Tester", role="tester")}
    orig_runsync = TR.task_router.run_sync
    def runsync_reject(sub, agent, m):
        if "ออกแบบ" in sub.message:
            raise TR._Rejected("ผู้ใช้ปฏิเสธ: เขียนไฟล์ design")
        return "ทำเสร็จ"
    TR.task_router.run_sync = runsync_reject
    try:
        out = svc.run(TaskLog(message="สร้างเกม", agent_id=prod.id, agent_name=prod.name), prod, {}, loop=None)
    finally:
        TR.task_router.run_sync = orig_runsync
    check("orchestrator: reject → header 'งานยังไม่ครบ'", "ยังไม่ครบ" in out)
    check("orchestrator: skip ขั้นที่เหลือหลัง reject", "⏭️" in out and "❌" in out)
    check("orchestrator: ไม่หลอกว่าเสร็จสมบูรณ์", "เสร็จ 0/3" in out or "สำเร็จ 0/3" in out)

    # 6) _expects_file
    check("_expects_file: 'เขียนโค้ดเกม'", O._expects_file("เขียนโค้ดเกม main.py"))
    check("_expects_file: งานคุย → False", not O._expects_file("ช่วยคิดไอเดียคุยกัน"))

    print()
    if _FAILS:
        print(f"M19-5 QA: {len(_FAILS)} FAILED -> {_FAILS}")
        return 1
    print("M19-5 QA: ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
