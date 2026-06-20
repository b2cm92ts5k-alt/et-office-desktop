"""ProposalService — เก็บ/ตอบ proposal จาก agent social loop (M3-10)
approve แล้ว trigger CrewAI Crew ทำงานจริง + broadcast ให้ Godot (M3-11)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from ..database import ProposalRow, get_session
from ..models.schemas import Proposal, TaskLog
from .agent_registry import registry
from .log_service import log_service
from .permission_gate import permission_gate
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

    # --- M13-3: approved proposal → ทำงานจริงผ่าน tool-loop (ToolExecutor + permission gate) ---

    async def _execute(self, proposal: Proposal) -> None:
        """รัน lead agent ผ่าน task_router.run_sync — เส้นทางเดียวกับงานปกติ จึงสร้าง/แก้
        ไฟล์ใน workspace ได้จริง (ไม่ใช่แค่ตอบ text แบบ crew เดิม) และทุก action ผ่าน
        permission gate ตามกฎเหล็ก M6. CEO ไม่ลงมือเอง → คัดออกจากผู้ลงมือ (M13-8)"""
        from .task_router import task_router  # lazy — กัน circular import

        agents = [a for pid in proposal.proposed_by if (a := registry.get(pid)) and not a.is_ceo]
        if not agents:
            agents = [a for a in registry.all() if not a.is_ceo][:1]  # ผู้เสนอถูกลบ → ตัวอื่นรับช่วง
        if not agents:
            log_service.add("error", f"proposal {proposal.id}: ไม่มี agent รับงาน")
            return
        lead = agents[0]
        brief = f"{proposal.title}\n\nรายละเอียด: {proposal.detail or '-'}"
        task = TaskLog(
            message=f"[ข้อเสนอที่ทีมอนุมัติแล้ว] ลงมือทำให้เกิดผลจริงในworkspace:\n{brief}",
            agent_id=lead.id, agent_name=lead.name, status="working")
        log_service.save_task(task)

        for a in agents:
            await self._set_status(a.id, "working")
        metrics: dict = {}
        try:
            output = await asyncio.to_thread(task_router.run_sync, task, lead, metrics)
            task.status, task.output, task.finished_at = "completed", output, _now()
            log_service.save_task(task)
            log_service.add("task", f"proposal {proposal.id} เสร็จ: {proposal.title[:80]}", lead.id)
            await ws_manager.broadcast({
                "type": "proposal.completed",
                "data": {"proposal_id": proposal.id, "title": proposal.title,
                         "agent_id": lead.id, "agent_ids": [a.id for a in agents],
                         "output": output},
            })
        except Exception as exc:
            task.status, task.output, task.finished_at = "failed", str(exc), _now()
            log_service.save_task(task)
            log_service.add("error", f"proposal {proposal.id} execution failed: {exc}", lead.id)
            await ws_manager.broadcast({
                "type": "proposal.failed",
                "data": {"proposal_id": proposal.id, "title": proposal.title,
                         "agent_id": lead.id, "error": str(exc)},
            })
        finally:
            permission_gate.finish_task(task.task_id)  # ล้างสิทธิ์อนุมัติยกชุด (M6-8)
            for a in agents:
                await self._set_status(a.id, "idle")

    async def _set_status(self, agent_id: str, status: str) -> None:
        registry.set_status(agent_id, status)
        await ws_manager.broadcast({
            "type": "agent.status",
            "data": {"agent_id": agent_id, "status": status},
        })


proposal_service = ProposalService()
