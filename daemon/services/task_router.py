"""TaskRouter — route user message → agent ที่เหมาะ → CrewAI execution (M1-8)

Flow (ตาม technical blueprint §04):
  1. keyword match หา agent
  2. broadcast task.routing
  3. สร้าง CrewAI Agent/Task/Crew ด้วย LLM ของ agent นั้น
  4. broadcast agent.status=working → Godot เล่นอนิเมชัน
  5. kickoff ใน thread (sync) → broadcast task.completed
  6. broadcast agent.status=idle
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from crewai import Agent, Crew, Process, Task

from ..adapters.llm_adapter import get_llm
from ..models.schemas import AgentConfig, TaskLog
from .agent_registry import registry
from .log_service import log_service
from .ws_manager import ws_manager


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
            output = await asyncio.to_thread(self._run_crew, task.message, agent_cfg)
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
            await self._set_status(agent_cfg.id, "idle")

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
