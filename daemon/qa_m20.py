"""M20-5 QA Gate — Orchestration Quality

offline: ตรวจ shared context (M20-1), per-kind verify (M20-2), output kind classify.
รัน: .venv\\Scripts\\python.exe daemon\\qa_m20.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daemon.models.schemas import AgentConfig, LLMConfig, TaskLog  # noqa: E402
from daemon.services import orchestrator_service as O  # noqa: E402
from daemon.services import task_router as TR  # noqa: E402

_FAILS: list[str] = []


def check(name, cond):
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        _FAILS.append(name)


def main() -> int:
    # 1) _output_kind (M20-2) — แยกชนิดไฟล์จริง
    ok = TR._output_kind
    check("output_kind: .png → image", ok("write_file", {"path": "a/x.png"}, "เขียนแล้ว") == "image")
    check("output_kind: .wav → audio", ok("write_file", {"path": "s.wav"}, "เขียนแล้ว") == "audio")
    check("output_kind: .cs → code", ok("write_file", {"path": "P.cs"}, "เขียนแล้ว") == "code")
    check("output_kind: .md → file", ok("write_file", {"path": "plan.md"}, "เขียนแล้ว") == "file")
    check("output_kind: generate_image สำเร็จ → image", ok("generate_image", {}, "สร้างรูปแล้ว 1 ไฟล์") == "image")
    check("output_kind: generate_image ล้ม → None", ok("generate_image", {}, "สร้างรูปไม่สำเร็จ") is None)

    # 2) _expected_kind (M20-2) — ดู role เป็นหลัก (แก้เคส LLM เขียน subtask หลากหลาย)
    art = AgentConfig(name="ET Artist", role="Game Artist / Animator")
    snd = AgentConfig(name="ET Sound Designer", role="Sound Designer")
    dev = AgentConfig(name="ET Developer", role="Game Developer")
    dsg = AgentConfig(name="ET Game Designer", role="Game Designer")
    # เคสจริงที่เคยหลุด: Artist subtask ไม่มีคำว่า "วาด" แต่ต้องรู้ว่าต้องได้ภาพ
    check("expected(role artist): 'สร้างสเก็ตช์และโมเดล 3D' → image", O._expected_kind(art, "สร้างสเก็ตช์และโมเดล 3D ของตัวละคร") == "image")
    check("expected(role sound): 'ออกแบบเสียงพื้นหลัง' → audio", O._expected_kind(snd, "ออกแบบเสียงพื้นหลัง") == "audio")
    check("expected(role dev): 'พัฒนาระบบควบคุม' → code", O._expected_kind(dev, "พัฒนาระบบควบคุมการเคลื่อนที่") == "code")
    check("expected(role designer): 'ออกแบบตัวละคร' → None (เอกสาร ไม่บังคับภาพ)", O._expected_kind(dsg, "ออกแบบตัวละครและระบบเกม") is None)

    # 3) shared context (M20-1) มีเป้าหมายเดิม + งานคนก่อน
    ctx = O._subtask_context('สร้างเกม mario', ["ET Designer (done): ออกแบบ → ได้ GDD"])
    check("context: มีเป้าหมายเดิม (mario)", "mario" in ctx)
    check("context: มีสรุปงานคนก่อน", "ET Designer" in ctx)

    # 4) orchestrator per-kind verify: artist(image) ได้แต่ .md → incomplete + header honest
    svc = O.orchestrator_service
    plan = [{"role": "designer", "subtask": "ออกแบบ GDD"},
            {"role": "artist", "subtask": "วาดภาพตัวละครหลัก"},
            {"role": "coder", "subtask": "เขียนโค้ดเกม"}]
    svc._decompose = lambda *a, **k: plan
    O._workspace_files = lambda limit=40: []   # mock (ไม่มี workspace ในเทส)
    O.ws_manager.broadcast_threadsafe = lambda *a, **k: None
    prod = AgentConfig(name="ET Producer", role="Producer", llm=LLMConfig(provider="ollama", model="qwen3:8b"))
    O.registry._agents = {prod.id: prod,
                          "d": AgentConfig(name="ET Designer", role="designer"),
                          "a": AgentConfig(name="ET Artist", role="artist"),
                          "c": AgentConfig(name="ET Developer", role="coder")}
    # run_sync จำลอง: designer→.md(file), artist→.md เท่านั้น(ไม่มีภาพ), coder→code
    kinds_by_role = {"designer": ["file"], "artist": ["file"], "coder": ["code"]}
    def fake_runsync(sub, agent, m):
        m["produced_kinds"] = kinds_by_role.get(agent.role, [])
        m["produced_output"] = bool(m["produced_kinds"])
        return "ทำเสร็จแล้วครับ"
    orig = TR.task_router.run_sync
    TR.task_router.run_sync = fake_runsync
    try:
        out = svc.run(TaskLog(message="สร้างเกม mario", agent_id=prod.id, agent_name=prod.name), prod, {}, loop=None)
    finally:
        TR.task_router.run_sync = orig
    check("verify: artist(ภาพ) ได้แต่ .md → ขึ้น 'งานยังไม่ครบ'", "ยังไม่ครบ" in out)
    check("verify: ระบุ artist ⚠️ (image ขาด)", "ET Artist" in out and "⚠️" in out)
    check("verify: designer/coder ผ่าน (✅)", out.count("✅") >= 2)

    print()
    if _FAILS:
        print(f"M20-5 QA: {len(_FAILS)} FAILED -> {_FAILS}")
        return 1
    print("M20-5 QA: ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
