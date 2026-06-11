"""/proposals — ดู/ตอบข้อเสนอจาก agent social loop (M3-10)"""
from typing import Optional

from fastapi import APIRouter, HTTPException

from ..models.schemas import Proposal, ProposalCreate, ProposalRespond
from ..services.proposal_service import proposal_service

router = APIRouter(tags=["proposals"])


@router.get("/proposals")
def list_proposals(status: Optional[str] = None, limit: int = 50) -> list[Proposal]:
    return proposal_service.list(status=status, limit=limit)


@router.post("/proposals")
async def create_proposal(payload: ProposalCreate) -> Proposal:
    """สร้างเอง (sidebar/ทดสอบ) — ปกติ proposal มาจาก social loop"""
    return await proposal_service.create(
        title=payload.title, detail=payload.detail, proposed_by=payload.proposed_by)


@router.post("/proposals/respond")
async def respond_proposal(payload: ProposalRespond) -> Proposal:
    proposal = await proposal_service.respond(
        payload.proposal_id, payload.action, payload.note)
    if proposal is None:
        raise HTTPException(404, "ไม่พบ proposal หรือถูกตอบไปแล้ว")
    return proposal
