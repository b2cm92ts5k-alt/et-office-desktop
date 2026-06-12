"""TaskRouter — route user message → agent ที่เหมาะ → execution (M1-8, M6-9)

Flow (ตาม technical blueprint §04):
  1. keyword match หา agent
  2. broadcast task.routing
  3. ถ้าตั้ง workspace แล้ว (M6-6) → tool loop แบบ JSON action protocol (M6-9)
     ไม่งั้น → CrewAI Crew แชทธรรมดาแบบเดิม
  4. broadcast agent.status=working → Godot เล่นอนิเมชัน
  5. รันใน thread (sync) → broadcast task.completed
  6. broadcast agent.status=idle

ทำไม JSON protocol ไม่ใช่ native tool-calling: qwen3:8b เรียก function หลายขั้น
ผ่าน LiteLLM ไม่เสถียร (Risk register) — บังคับตอบ JSON ทีละ action แล้ว parse เอง
ตรงไปตรงมาและ debug ง่ายกว่า | task ซับซ้อนแนะนำสลับ agent เป็น cloud model (M4-6)
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone

from crewai import Agent, Crew, Process, Task

from ..adapters.llm_adapter import get_llm
from ..models.schemas import AgentConfig, TaskLog
from .agent_registry import registry
from .log_service import log_service
from .permission_gate import permission_gate
from .settings_store import settings_store
from .tool_executor import TOOLS_SPEC, WorkspaceError, execute, summarize, workspace_root
from .ws_manager import ws_manager

MAX_STEPS = 10          # action สูงสุดต่อ task — กัน loop ไม่รู้จบ
MAX_PARSE_FAILS = 2     # LLM ตอบไม่เป็น JSON กี่ครั้งถึงยอมรับเป็นคำตอบ text

_TOOL_LINES = "\n".join(
    f"- {name}({', '.join(spec['args'])}) — {spec['desc']}"
    for name, spec in TOOLS_SPEC.items())

_LOOP_PROMPT = """{system_prompt}

คุณทำงานอยู่ใน workspace: {root}
เครื่องมือที่ใช้ได้:
{tools}

ตอบเป็น JSON เท่านั้น เลือกรูปแบบใดรูปแบบหนึ่ง:
1. ทำ action ถัดไป (ทีละ 1 action):
{{"thought": "คิดสั้น ๆ", "action": {{"tool": "ชื่อ tool", "args": {{...}}}}}}
2. งานเสร็จแล้ว:
{{"final": "สรุปผลถึงผู้ใช้ ภาษาเดียวกับผู้ใช้"}}

กติกา:
- path ใช้แบบ relative ใต้ workspace เท่านั้น เช่น "docs/plan.md"
- ทุก action ต้องรอผู้ใช้อนุญาต — ถ้าโดนปฏิเสธ ให้ปรับแผนหรือสรุปเท่าที่ทำได้
- ห้ามตอบ final ว่า "ทำแล้ว" ถ้ายังไม่มี OBSERVATION ยืนยันว่า action สำเร็จจริง
- เฉพาะคำถามคุยเฉย ๆ ที่ไม่ต้องแตะไฟล์/รันคำสั่ง ถึงตอบ final ได้ทันที

ตัวอย่าง: ผู้ใช้สั่ง "สร้างไฟล์ a.txt เนื้อหา hi"
คุณ:   {{"thought": "ต้องเขียนไฟล์", "action": {{"tool": "write_file", "args": {{"path": "a.txt", "content": "hi"}}}}}}
ระบบ:  OBSERVATION: เขียนแล้ว: a.txt (2 ตัวอักษร)
คุณ:   {{"final": "สร้างไฟล์ a.txt เรียบร้อยแล้วครับ"}}"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_json(text: str) -> dict | None:
    """ดึง JSON object แรกจากคำตอบ LLM — ตัด <think> ของ qwen3 ก่อน"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    decoder = json.JSONDecoder()
    i = text.find("{")
    while i != -1:
        try:
            obj, _ = decoder.raw_decode(text[i:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        i = text.find("{", i + 1)
    return None


class TaskRouter:
    async def route_and_execute(self, message: str) -> TaskLog:
        """สร้าง task แล้วรันเบื้องหลัง — return ทันทีพร้อม task_id"""
        agent_cfg = self._match_agent(message)
        task = TaskLog(message=message, agent_id=agent_cfg.id, agent_name=agent_cfg.name)
        log_service.save_task(task)
        log_service.add("task", f"routing → {agent_cfg.name}: {message[:120]}", agent_cfg.id)

        await ws_manager.broadcast({
            "type": "task.routing",
            "data": {"task_id": task.task_id, "agent_id": agent_cfg.id,
                     "agent": agent_cfg.name, "message": message},
        })
        asyncio.create_task(self._execute(task, agent_cfg))
        return task

    def _match_agent(self, message: str) -> AgentConfig:
        """keyword match — agent ที่ keyword ตรงมากสุดชนะ, เสมอ/ไม่เจอ → ตัวแรก"""
        agents = registry.all()
        if not agents:
            raise RuntimeError("ไม่มี agent ใน registry")
        lower = message.lower()
        best, best_score = agents[0], 0
        for a in agents:
            score = sum(1 for kw in a.keywords if kw.lower() in lower)
            if score > best_score:
                best, best_score = a, score
        return best

    async def _execute(self, task: TaskLog, agent_cfg: AgentConfig) -> None:
        await self._set_status(agent_cfg.id, "working")
        task.status = "working"
        log_service.save_task(task)

        try:
            output = await asyncio.to_thread(self._run_agent, task, agent_cfg)
            task.status = "completed"
            task.output = output
            task.finished_at = _now()
            log_service.save_task(task)
            log_service.add("task", f"completed: {task.task_id}", agent_cfg.id)
            await ws_manager.broadcast({
                "type": "task.completed",
                "data": {"task_id": task.task_id, "agent_id": agent_cfg.id, "output": output},
            })
        except Exception as exc:  # LLM/network error — แจ้งทุก layer แล้ว agent กลับ idle
            task.status = "failed"
            task.output = str(exc)
            task.finished_at = _now()
            log_service.save_task(task)
            log_service.add("error", f"task {task.task_id} failed: {exc}", agent_cfg.id)
            await ws_manager.broadcast({
                "type": "task.failed",
                "data": {"task_id": task.task_id, "agent_id": agent_cfg.id, "error": str(exc)},
            })
        finally:
            permission_gate.finish_task(task.task_id)  # ล้างสิทธิ์อนุมัติยกชุด (M6-8)
            await self._set_status(agent_cfg.id, "idle")

    def _run_agent(self, task: TaskLog, agent_cfg: AgentConfig) -> str:
        """sync — เลือกเส้นทาง: workspace ตั้งแล้ว → tool loop, ไม่งั้นแชทผ่าน Crew"""
        if str(settings_store.get("workspace_path") or "").strip():
            return self._run_tool_loop(task, agent_cfg)
        return self._run_crew(task.message, agent_cfg)

    def _run_tool_loop(self, task: TaskLog, agent_cfg: AgentConfig) -> str:
        """JSON action protocol (M6-9) — LLM ตอบทีละ action ผ่าน permission gate เสมอ"""
        try:
            root = workspace_root()
        except WorkspaceError as exc:
            return f"ใช้ workspace ไม่ได้: {exc}"
        llm = get_llm(agent_cfg.llm, temperature=0.2)  # tool loop ต้องนิ่ง ไม่ใช่สร้างสรรค์
        system = _LOOP_PROMPT.format(
            system_prompt=agent_cfg.system_prompt or f"คุณคือ {agent_cfg.name} ({agent_cfg.role})",
            root=str(root), tools=_TOOL_LINES)
        messages: list[dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": task.message},
        ]
        parse_fails = 0
        actions_done = 0
        final_pushback = False
        for _step in range(MAX_STEPS):
            raw = str(llm.call(messages))
            data = _extract_json(raw)

            if data is None:
                parse_fails += 1
                if parse_fails > MAX_PARSE_FAILS:
                    # ตอบ text ตลอด = model ตั้งใจคุยเฉย ๆ — ส่งเป็นคำตอบไปเลย
                    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user",
                                 "content": "ตอบเป็น JSON ตามรูปแบบที่กำหนดเท่านั้น"})
                continue

            if "final" in data:
                # กัน model เล็กอ้างว่า "ทำแล้ว" ทั้งที่ยังไม่มี action — ดันกลับ 1 ครั้ง
                # ถ้าเป็นแชทเฉย ๆ model จะยืนยัน final ซ้ำแล้วผ่านได้
                if actions_done == 0 and not final_pushback:
                    final_pushback = True
                    messages.append({"role": "assistant", "content": raw})
                    messages.append({"role": "user", "content":
                        "ยังไม่มี action ใดถูกทำเลย — ถ้างานนี้ต้องสร้าง/แก้ไฟล์หรือรันคำสั่ง "
                        "ให้ส่ง action ก่อน ถ้าเป็นคำถามคุยเฉย ๆ ให้ตอบ final เดิมซ้ำอีกครั้ง"})
                    continue
                return str(data["final"])

            action = data.get("action") or {}
            tool = str(action.get("tool", ""))
            args = action.get("args") or {}
            if tool not in TOOLS_SPEC:
                observation = f"ไม่รู้จัก tool '{tool}' — ที่มี: {', '.join(TOOLS_SPEC)}"
            else:
                summary = summarize(tool, args)
                detail = json.dumps(args, ensure_ascii=False)[:2000]
                approved = permission_gate.request(
                    task.task_id, agent_cfg.id, agent_cfg.name, tool, summary, detail)
                if approved:
                    try:
                        observation = execute(tool, args)
                        actions_done += 1
                    except WorkspaceError as exc:
                        observation = f"โดนบล็อค: {exc}"
                else:
                    observation = "ผู้ใช้ปฏิเสธ action นี้ — ปรับแผน หรือสรุปงานเท่าที่ทำได้"

            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": f"OBSERVATION:\n{observation}"})

        return "หยุดที่เพดาน %d actions — งานอาจยังไม่จบ ลองสั่งต่อหรือแบ่งงานให้เล็กลง" % MAX_STEPS

    def _run_crew(self, message: str, agent_cfg: AgentConfig) -> str:
        """sync — รันใน thread เพื่อไม่ block event loop"""
        crew_agent = Agent(
            role=agent_cfg.role,
            goal=agent_cfg.system_prompt or f"ช่วยเหลือ user ในฐานะ {agent_cfg.role}",
            backstory=agent_cfg.backstory or f"คุณคือ {agent_cfg.name} ทีมงาน ET Office",
            llm=get_llm(agent_cfg.llm),
            verbose=False,
        )
        crew_task = Task(
            description=message,
            agent=crew_agent,
            expected_output="คำตอบที่สมบูรณ์สำหรับคำขอของ user (ภาษาเดียวกับ user)",
        )
        crew = Crew(agents=[crew_agent], tasks=[crew_task],
                    process=Process.sequential, verbose=False)
        result = crew.kickoff()
        return getattr(result, "raw", str(result))

    async def _set_status(self, agent_id: str, status: str) -> None:
        registry.set_status(agent_id, status)
        await ws_manager.broadcast({
            "type": "agent.status",
            "data": {"agent_id": agent_id, "status": status},
        })


task_router = TaskRouter()
