"""/task + /tasks (M1-9)"""
from fastapi import APIRouter

from ..models.schemas import TaskLog, TaskRequest
from ..services.log_service import log_service
from ..services.task_router import task_router

router = APIRouter(tags=["tasks"])


@router.post("/task")
async def submit_task(payload: TaskRequest) -> dict:
    task = await task_router.route_and_execute(payload.message)
    return {"task_id": task.task_id, "agent": task.agent_name}


@router.get("/tasks")
def list_tasks(limit: int = 50) -> list[TaskLog]:
    return log_service.list_tasks(limit)
