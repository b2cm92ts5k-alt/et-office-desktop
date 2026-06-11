"""POST /event — push custom event เข้า hub สำหรับ integration ภายนอก (M1-14)"""
from fastapi import APIRouter

from ..models.schemas import OEPEvent
from ..services.ws_manager import ws_manager

router = APIRouter(tags=["events"])


@router.post("/event")
async def push_event(event: OEPEvent) -> dict:
    await ws_manager.broadcast(event.model_dump())
    return {"broadcast": True}
