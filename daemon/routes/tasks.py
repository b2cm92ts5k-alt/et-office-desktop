"""/task + /tasks (M1-9) + /chat (M13-7) + /tasks/{id}/continue (M21-2)"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..models.schemas import TaskLog, TaskRequest
from ..services.log_service import log_service
from ..services.orchestration_store import orchestration_store
from ..services.task_router import task_router

router = APIRouter(tags=["tasks"])


class TargetedTaskRequest(TaskRequest):
    """M13-7 — terminal เลือกผู้รับตรง ๆ ได้ (ว่าง = keyword routing เดิม)"""
    agent_id: str = ""
    single: bool = False   # M23-3 — โหมดเดี่ยว (1 agent ทำเอง ไม่แตกทีม); ใช้เมื่อไม่เลือกผู้รับ


class ChatRequest(BaseModel):
    """M13-7 — คุยเล่นกับ agent ตัวที่เลือก"""
    message: str
    agent_id: str = ""


@router.post("/task")
async def submit_task(payload: TargetedTaskRequest) -> dict:
    task = await task_router.route_and_execute(
        payload.message, payload.agent_id or None, single=payload.single)
    # model จริงของผู้รับ ณ ตอนนี้ (authoritative) — กัน terminal โชว์ model เก่าจาก cache (fix 2026-06-21)
    from ..services.agent_registry import registry
    a = registry.get(task.agent_id)
    # orchestrate = ไม่เลือกผู้รับ และ ไม่ใช่โหมดเดี่ยว (M23-3)
    return {"task_id": task.task_id, "agent": task.agent_name, "agent_id": task.agent_id,
            "model": (a.llm.model if a else ""), "provider": (a.llm.provider if a else ""),
            "orchestrate": not bool(payload.agent_id) and not payload.single}


@router.post("/chat")
async def chat(payload: ChatRequest) -> dict:
    """คุยเล่นกับ agent — ตอบสนทนา, ถ้าผู้ใช้ขอให้ทำงานจริงจะ escalate เป็น task ให้ (M13-7)"""
    return await task_router.chat(payload.message, payload.agent_id or None)


@router.get("/tasks")
def list_tasks(limit: int = 50) -> list[TaskLog]:
    return log_service.list_tasks(limit)


@router.post("/tasks/{task_id}/continue")
async def continue_task(task_id: str) -> dict:
    """M21-2 — ทำงานต่อจากเดิม: รันเฉพาะขั้นที่ยังไม่เสร็จของงาน orchestration เดิม"""
    try:
        task = await task_router.continue_orchestration(task_id)
    except KeyError:
        raise HTTPException(404, "ไม่พบสถานะงานเดิมให้ทำต่อ (อาจรีสตาร์ทแล้ว หรือเก่าเกินไป)")
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {"task_id": task.task_id, "agent": task.agent_name, "agent_id": task.agent_id,
            "orchestrate": True, "continued": True}


@router.get("/tasks/{task_id}/state")
def task_state(task_id: str) -> dict:
    """M21-1 — สถานะแต่ละขั้นของงาน orchestration (ใช้รู้ว่ามีขั้นค้างให้ทำต่อไหม)"""
    state = orchestration_store.get(task_id)
    if not state:
        raise HTTPException(404, "ไม่พบสถานะงาน")
    return state


@router.get("/orchestrations")
def list_orchestrations(limit: int = 20) -> list[dict]:
    """M21-1 — รายการงาน orchestration ล่าสุด (สรุป) — UI แสดงรายการที่ทำต่อได้"""
    return orchestration_store.list(limit)
