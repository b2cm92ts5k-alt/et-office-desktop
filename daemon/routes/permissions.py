"""/permissions — คิวขออนุญาต action ของ agent (M6-8)"""
from fastapi import APIRouter, HTTPException

from ..models.schemas import PermissionRespond
from ..services.permission_gate import permission_gate

router = APIRouter(tags=["permissions"])


@router.get("/permissions")
def list_pending() -> list[dict]:
    """คำขอที่ค้างอยู่ — sidebar โหลดตอน reconnect กันพลาด event"""
    return permission_gate.pending()


@router.post("/permissions/respond")
def respond(payload: PermissionRespond) -> dict:
    if not permission_gate.respond(payload.request_id, payload.decision):
        raise HTTPException(404, "คำขอหมดอายุหรือถูกตอบไปแล้ว")
    return {"ok": True}
