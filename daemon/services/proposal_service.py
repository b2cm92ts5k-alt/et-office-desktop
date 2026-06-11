"""ProposalService — เก็บ/ตอบ proposal จาก agent social loop (M3-10)
approve แล้ว trigger CrewAI Crew ทำงานจริง + broadcast ให้ Godot (M3-11)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from crewai import Agent, Crew, Process, Task

from ..adapters.llm_adapter import get_llm
from ..database import ProposalRow, get_session
from ..models.schemas import AgentConfig, Proposal, TaskLog
from .agent_registry import registry
from .log_service import log_service
from .ws_manager import ws_manager


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_proposal(row: ProposalRow) -> Proposal:
    return Proposal(
        id=row.proposal_id, title=row.title, detail=row.detail,
        proposed_by=[p for p in (row.proposed_by or "").split(",") if p],
        status=row.status, note=row.note, created_at=row.created_at,
    )


class ProposalService:
    async def create(self, title: str, detail: str, proposed_by: list[str]) -> Proposal:
        proposal = Proposal(title=title, detail=detail, proposed_by=proposed_by)
        with get_session() as s:
            s.add(ProposalRow(
                proposal_id=proposal.id, title=proposal.title, detail=proposal.detail,
                proposed_by=",".join(proposed_by), status=proposal.status,
                created_at=proposal.created_at,
            ))
            s.commit()
        names = [a.name for pid in proposed_by if (a := registry.get(pid))]
        log_service.add("social", f"proposal: {title[:120]} (โดย {', '.join(names)})")
        await ws_manager.broadcast({
            "type": "proposal.created",
            "data": {"proposal_id": proposal.id, "title": title,
                     "proposed_by": proposed_by},
        })
        return proposal

    def list(self, status: Optional[str] = None, limit: int = 50) -> list[Proposal]:
        with get_session() as s:
            q = s.query(ProposalRow)
            if status:
                q = q.filter(ProposalRow.status == status)
            rows = q.order_by(ProposalRow.id.desc()).limit(limit).all()
            return [_to_proposal(r) for r in rows]

    def get(self, proposal_id: str) -> Optional[Proposal]:
        with get_session() as s:
            row = s.query(ProposalRow).filter(
                ProposalRow.proposal_id == proposal_id).first()
            return _to_proposal(row) if row else None

    def seconds_since_last(self) -> Optional[float]:
        """อายุ proposal ล่าสุด (วินาที) — ใช้เช็ค cooldown ใน social loop"""
        with get_session() as s:
            row = s.query(ProposalRow).order_by(ProposalRow.id.desc()).first()
            if row is None or not row.created_at:
                return None
            created = datetime.fromisoformat(row.created_at)
            return (datetime.now(timezone.utc) - created).total_seconds()

    async def respond(self, proposal_id: str, action: str, note: str = "") -> Optional[Proposal]:
        """approve/reject — approve แล้วรัน Crew เบื้องหลัง (M3-11)"""
        with get_session() as s:
            row = s.query(ProposalRow).filter(
                ProposalRow.proposal_id == proposal_id).first()
            if row is None or row.status != "pending":
                return None
            row.status = "approved" if action == "approve" else "rejected"
            row.note = note
            s.commit()
            proposal = _to_proposal(row)

        log_service.add("social", f"proposal {proposal_id} → {proposal.status}")
        await ws_manager.broadcast({
            "type": f"proposal.{proposal.status}",
            "data": {"proposal_id": proposal_id, "title": proposal.title, "note": note},
        })
        if proposal.status == "approved":
            asyncio.create_task(self._execute(proposal))
        return proposal

    # --- M3-11: approved proposal → CrewAI ทำงานจริง ---

    async def _execute(self, proposal: Proposal) -> None:
        agents = [a for pid in proposal.proposed_by if (a := registry.get(pid))]
        if not agents:
            agents = registry.all()[:1]  # ผู้เสนอถูกลบไปแล้ว → ตัวแรกรับช่วง
        task = TaskLog(message=f"[proposal] {proposal.title}",
                       agent_id=agents[0].id, agent_name=agents[0].name,
                       status="working")
        log_service.save_task(task)

        for a in agents:
            await self._set_status(a.id, "working")
        try:
            output = await asyncio.to_thread(self._run_crew, proposal, agents)
            task.status, task.output, task.finished_at = "completed", output, _now()
            log_service.save_task(task)
            await ws_manager.broadcast({
                "type": "proposal.completed",
                "data": {"proposal_id": proposal.id, "title": proposal.title,
                         "agent_ids": [a.id for a in agents], "output": output},
            })
        except Exception as exc:
            task.status, task.output, task.finished_at = "failed", str(exc), _now()
            log_service.save_task(task)
            log_service.add("error", f"proposal {proposal.id} execution failed: {exc}")
            await ws_manager.broadcast({
                "type": "proposal.failed",
                "data": {"proposal_id": proposal.id, "error": str(exc)},
            })
        finally:
            for a in agents:
                await self._set_status(a.id, "idle")

    def _run_crew(self, proposal: Proposal, agents: list[AgentConfig]) -> str:
        """sync ใน thread — lead วางแผน, partner ลงมือต่อ (ถ้ามี)"""
        crew_agents = [Agent(
            role=a.role,
            goal=a.system_prompt or f"ช่วยเหลือทีมในฐานะ {a.role}",
            backstory=a.backstory or f"คุณคือ {a.name} ทีมงาน ET Office",
            llm=get_llm(a.llm), verbose=False,
        ) for a in agents]

        brief = f"{proposal.title}\n\nรายละเอียด: {proposal.detail or '-'}"
        tasks = [Task(
            description=f"ทีมอนุมัติข้อเสนอนี้แล้ว ลงมือทำให้เกิดผลจริง:\n{brief}",
            agent=crew_agents[0],
            expected_output="ผลงานตามข้อเสนอ พร้อมสรุปสั้น ๆ ว่าได้อะไร (ภาษาไทย)",
        )]
        if len(crew_agents) > 1:
            tasks.append(Task(
                description="ตรวจและต่อยอดผลงานจากเพื่อนร่วมทีม ให้สมบูรณ์พร้อมใช้",
                agent=crew_agents[1],
                expected_output="ผลงานฉบับสมบูรณ์ (ภาษาไทย)",
            ))
        crew = Crew(agents=crew_agents, tasks=tasks,
                    process=Process.sequential, verbose=False)
        result = crew.kickoff()
        return getattr(result, "raw", str(result))

    async def _set_status(self, agent_id: str, status: str) -> None:
        registry.set_status(agent_id, status)
        await ws_manager.broadcast({
            "type": "agent.status",
            "data": {"agent_id": agent_id, "status": status},
        })


proposal_service = ProposalService()
