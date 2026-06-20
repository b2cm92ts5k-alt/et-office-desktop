"""/agents CRUD (M1-6)"""
from fastapi import APIRouter, HTTPException

from ..models.schemas import AgentConfig, AgentCreate, AgentUpdate
from ..services.agent_registry import registry
from ..services.ws_manager import ws_manager

router = APIRouter(tags=["agents"])


@router.get("/agents")
def list_agents() -> list[AgentConfig]:
    return registry.all()


@router.post("/agents")
async def create_agent(payload: AgentCreate) -> AgentConfig:
    agent = registry.create(payload)
    await ws_manager.broadcast({"type": "agent.created", "data": agent.model_dump()})
    return agent


@router.put("/agents/{agent_id}")
async def update_agent(agent_id: str, payload: AgentUpdate) -> AgentConfig:
    agent = registry.update(agent_id, payload)
    if not agent:
        raise HTTPException(404, "agent not found")
    await ws_manager.broadcast({"type": "agent.updated", "data": agent.model_dump()})
    return agent


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str) -> dict:
    if not registry.delete(agent_id):
        raise HTTPException(404, "agent not found")
    from ..services.memory_service import memory_service
    memory_service.clear_agent(agent_id)  # M11-11 — ไล่ออกแล้วล้างความจำส่วนตัวด้วย
    await ws_manager.broadcast({"type": "agent.deleted", "data": {"agent_id": agent_id}})
    return {"deleted": True}
