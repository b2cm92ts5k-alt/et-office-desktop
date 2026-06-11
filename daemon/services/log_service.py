"""LogService — เขียน activity log ลง SQLite + query แบบ filter (M1-13)"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from ..database import LogRow, TaskRow, get_session
from ..models.schemas import LogEntry, TaskLog


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LogService:
    # --- activity logs ---

    def add(self, type: str, message: str, agent_id: str = "") -> None:
        with get_session() as s:
            s.add(LogRow(ts=_now(), agent_id=agent_id, type=type, message=message))
            s.commit()

    def query(
        self,
        agent_id: Optional[str] = None,
        type: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 200,
    ) -> list[LogEntry]:
        with get_session() as s:
            q = s.query(LogRow)
            if agent_id:
                q = q.filter(LogRow.agent_id == agent_id)
            if type:
                q = q.filter(LogRow.type == type)
            if since:
                q = q.filter(LogRow.ts >= since)
            rows = q.order_by(LogRow.id.desc()).limit(limit).all()
            return [
                LogEntry(id=r.id, ts=r.ts, agent_id=r.agent_id, type=r.type, message=r.message)
                for r in rows
            ]

    # --- task history ---

    def save_task(self, task: TaskLog) -> None:
        with get_session() as s:
            row = s.query(TaskRow).filter(TaskRow.task_id == task.task_id).first()
            if row is None:
                row = TaskRow(task_id=task.task_id)
                s.add(row)
            row.message = task.message
            row.agent_id = task.agent_id
            row.agent_name = task.agent_name
            row.status = task.status
            row.output = task.output
            row.created_at = task.created_at
            row.finished_at = task.finished_at
            s.commit()

    def list_tasks(self, limit: int = 50) -> list[TaskLog]:
        with get_session() as s:
            rows = s.query(TaskRow).order_by(TaskRow.id.desc()).limit(limit).all()
            return [
                TaskLog(
                    task_id=r.task_id, message=r.message, agent_id=r.agent_id,
                    agent_name=r.agent_name, status=r.status, output=r.output,
                    created_at=r.created_at, finished_at=r.finished_at,
                )
                for r in rows
            ]


log_service = LogService()
