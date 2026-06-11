"""GET /logs — activity log filter by agent/type/date (M1-13)"""
from typing import Optional

from fastapi import APIRouter

from ..models.schemas import LogEntry
from ..services.log_service import log_service

router = APIRouter(tags=["logs"])


@router.get("/logs")
def list_logs(
    agent_id: Optional[str] = None,
    type: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = 200,
) -> list[LogEntry]:
    return log_service.query(agent_id=agent_id, type=type, since=since, limit=limit)
