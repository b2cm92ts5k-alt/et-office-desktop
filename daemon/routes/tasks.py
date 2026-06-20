"""/task + /tasks (M1-9) + /chat (M13-7)"""
from fastapi import APIRouter
from pydantic import BaseModel

from ..models.schemas import TaskLog, TaskRequest
from ..services.log_service import log_service
from ..services.task_router import task_router

router = APIRouter(tags=["tasks"])


class TargetedTaskRequest(TaskRequest):
    """M13-7 — terminal เลือกผู้รับตรง ๆ ได้ (ว่าง = keyword routing เดิม)"""
    agent_id: str = ""


class ChatRequest(BaseModel):
    """M13-7 — คุยเล่นกับ agent ตัวที่เลือก"""
    message: str
    agent_id: str = ""


@router.post("/task")
async def submit_task(payload: TargetedTaskRequest) -> dict:
    task = await task_router.route_and_execute(payload.message, payload.agent_id or None)
    # model จริงของผู้รับ ณ ตอนนี้ (authoritative) — กัน terminal โชว์ model เก่าจาก cache (fix 2026-06-21)
    from ..services.agent_registry import registry
    a = registry.get(task.agent_id)
    return {"task_id": task.task_id, "agent": task.agent_name, "agent_id": task.agent_id,
            "model": (a.llm.model if a else ""), "provider": (a.llm.provider if a else ""),
            "orchestrate": not bool(payload.agent_id)}  # auto (ไม่เลือกผู้รับ) = แตกงาน


@router.post("/chat")
async def chat(payload: ChatRequest) -> dict:
    """คุยเล่นกับ agent — ตอบสนทนา, ถ้าผู้ใช้ขอให้ทำงานจริงจะ escalate เป็น task ให้ (M13-7)"""
    return await task_router.chat(payload.message, payload.agent_id or None)


@router.get("/tasks")
def list_tasks(limit: int = 50) -> list[TaskLog]:
    return log_service.list_tasks(limit)
