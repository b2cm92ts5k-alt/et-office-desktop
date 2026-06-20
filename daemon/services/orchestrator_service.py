"""OrchestratorService (M15-5) — Sub-Agent: Producer แตกงาน → มอบหมาย → รวมผล

หลักการเดียวของ ET Office (CEO เคาะ 2026-06-20): คำสั่งทั่วไปของ CEO เข้า orchestrator เสมอ
1. **decompose** — Producer ยิง LLM (constrained JSON) แตกเป็น subtask + เลือก role ที่เหมาะ
   (งานง่าย = 1 subtask). decompose แนะนำ cloud (D1) แต่ทำ local ได้ fallback.
2. **dispatch** — แต่ละ subtask → match agent ตาม role → `task_router.run_sync()` (reuse tool-loop
   + permission gate เดิม 100%) ตามลำดับ. broadcast ทุกขั้น → Godot โชว์ agent ทำงานทีละตัว.
3. **synthesize** — รวมผลทุก subtask → Producer เรียบเรียงคำตอบสุดท้ายให้ CEO.

reuse สูงสุด: subtask = tool-loop เดิม (+skill M15-1). โค้ดใหม่ = แค่ loop decompose/dispatch/synthesize.
import task_router แบบ lazy กัน circular (task_router เรียก orchestrator ใน _execute).
"""
from __future__ import annotations

import json

from ..models.schemas import AgentConfig, TaskLog
from .agent_registry import registry
from .log_service import log_service
from .ws_manager import ws_manager

MAX_SUBTASKS = 5   # กันแตกเยอะเกินจน token/เวลาบาน

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "role": {"type": "string"},
                    "subtask": {"type": "string"},
                },
                "required": ["role", "subtask"],
            },
        }
    },
    "required": ["plan"],
}


class OrchestratorService:
    def _team(self) -> list[AgentConfig]:
        """ทีมที่มอบงานได้ — ทุก agent ยกเว้น CEO (CEO ไม่ลงมือเอง M13-8)"""
        return [a for a in registry.all() if not a.is_ceo]

    def _pick_agent(self, role: str, subtask: str) -> AgentConfig | None:
        """หา agent ที่ role/keyword ตรงกับที่ plan ระบุ — ไม่เจอ → keyword match จาก subtask"""
        team = self._team()
        if not team:
            return None
        rl = (role or "").lower().strip()
        if rl:
            for a in team:
                if rl in a.role.lower() or rl in a.name.lower() or any(rl in k.lower() for k in a.keywords):
                    return a
        from .task_router import task_router
        picked = task_router._match_agent(subtask)
        return picked if not picked.is_ceo else (team[0] if team else None)

    def _decompose(self, message: str, producer: AgentConfig, metrics: dict) -> list[dict]:
        """แตกงานเป็น plan [{role, subtask}] — งานง่าย = 1 subtask. คืน [] ถ้าแตกไม่ได้"""
        roles = ", ".join(sorted({f"{a.role}" for a in self._team()})) or "ทั่วไป"
        sys = (
            "คุณคือหัวหน้าทีม (Producer) แตกคำสั่งของ CEO เป็นงานย่อยให้ลูกทีมทำ.\n"
            f"ลูกทีมที่มี (role): {roles}\n"
            f"กติกา: แตกเป็นงานย่อยที่ทำได้จริงไม่เกิน {MAX_SUBTASKS} ข้อ, เรียงตามลำดับการทำ, "
            "แต่ละข้อระบุ role ลูกทีมที่เหมาะและคำสั่งย่อยที่ชัดเจน. "
            "งานง่ายให้แตกแค่ 1 ข้อ. ตอบเป็น JSON ตาม schema เท่านั้น."
        )
        messages = [{"role": "system", "content": sys}, {"role": "user", "content": message}]
        from .task_router import _extract_json
        from ..adapters.llm_adapter import get_llm, ollama_chat
        from .cost_guard import cost_guard
        try:
            if producer.llm.provider == "ollama" or cost_guard.over_budget():
                raw = ollama_chat(messages, schema=PLAN_SCHEMA, temperature=0.3, stats=metrics, think=False)
                data = json.loads(raw)
            else:
                llm = get_llm(producer.llm, temperature=0.3)
                data = _extract_json(str(llm.call(messages))) or {}
        except Exception as exc:  # noqa: BLE001 — decompose ล้ม → คืน [] (caller fallback งานเดี่ยว)
            log_service.add("error", f"decompose ล้มเหลว: {str(exc)[:120]}", producer.id)
            return []
        plan = data.get("plan") if isinstance(data, dict) else None
        if not isinstance(plan, list):
            return []
        out = []
        for step in plan[:MAX_SUBTASKS]:
            if isinstance(step, dict) and step.get("subtask"):
                out.append({"role": str(step.get("role", "")), "subtask": str(step["subtask"])})
        return out

    def _synthesize(self, message: str, results: list[tuple], producer: AgentConfig, metrics: dict) -> str:
        """รวมผล subtask ทั้งหมด → คำตอบสุดท้ายให้ CEO"""
        if len(results) == 1:
            return results[0][2]   # งานเดี่ยว ไม่ต้องเรียบเรียงซ้ำ
        body = "\n\n".join(f"[{a.name} ({a.role})] {sub}\n→ {out}" for a, sub, out in results)
        sys = ("คุณคือ Producer สรุปผลงานที่ลูกทีมทำเสร็จให้ CEO ฟังแบบกระชับ เป็นระเบียบ "
               "บอกว่าได้อะไรบ้าง/เหลืออะไร ภาษาไทย /no_think")
        messages = [{"role": "system", "content": sys},
                    {"role": "user", "content": f"คำสั่งเดิม: {message}\n\nผลงานลูกทีม:\n{body}"}]
        from ..adapters.llm_adapter import get_llm, ollama_chat
        from .cost_guard import cost_guard
        try:
            if producer.llm.provider == "ollama" or cost_guard.over_budget():
                return ollama_chat(messages, temperature=0.4, stats=metrics, think=False)
            return str(get_llm(producer.llm, temperature=0.4).call(messages))
        except Exception:  # noqa: BLE001 — สรุปไม่ได้ → ส่งผลดิบรวมกัน
            return body

    def run(self, task: TaskLog, producer: AgentConfig, metrics: dict, loop) -> str:
        """แตกงาน → มอบหมาย → รวมผล (sync, เรียกจาก _execute ผ่าน to_thread)"""
        def emit(etype: str, data: dict) -> None:
            ws_manager.broadcast_threadsafe(loop, {"type": etype, "data": {"task_id": task.task_id, **data}})

        from .task_router import task_router
        from .permission_gate import permission_gate

        plan = self._decompose(task.message, producer, metrics)
        if not plan:   # decompose ล้ม → ทำงานเดี่ยวด้วย agent ที่ match (กันค้าง)
            agent = self._pick_agent("", task.message) or producer
            log_service.add("task", f"orchestrate: แตกงานไม่ได้ → ทำเดี่ยวโดย {agent.name}", producer.id)
            return task_router.run_sync(
                TaskLog(message=task.message, agent_id=agent.id, agent_name=agent.name), agent, metrics)

        log_service.add("task", f"orchestrate: {producer.name} แตกเป็น {len(plan)} งาน", producer.id)
        emit("orchestrate.plan", {"steps": [{"role": s["role"], "subtask": s["subtask"]} for s in plan]})

        results: list[tuple] = []
        for i, step in enumerate(plan, 1):
            agent = self._pick_agent(step["role"], step["subtask"])
            if agent is None:
                continue
            emit("orchestrate.subtask", {"index": i, "total": len(plan),
                                         "agent_id": agent.id, "agent": agent.name, "subtask": step["subtask"]})
            log_service.add("task", f"  {i}/{len(plan)} → {agent.name}: {step['subtask'][:80]}", agent.id)
            sub = TaskLog(message=step["subtask"], agent_id=agent.id, agent_name=agent.name)
            try:
                out = task_router.run_sync(sub, agent, metrics)
            except Exception as exc:  # noqa: BLE001 — subtask พัง → จดแล้วไปต่อ (ทีมไม่ล้มทั้งงาน)
                out = f"(ทำไม่สำเร็จ: {str(exc)[:100]})"
                log_service.add("error", f"subtask {i} โดย {agent.name} ล้มเหลว: {str(exc)[:100]}", agent.id)
            finally:
                permission_gate.finish_task(sub.task_id)
            results.append((agent, step["subtask"], out))
            emit("orchestrate.subtask.done", {"index": i, "agent_id": agent.id})

        return self._synthesize(task.message, results, producer, metrics)


orchestrator_service = OrchestratorService()
