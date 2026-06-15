"""MCP server management (M10-4) — เพิ่ม/ลบ/ดู MCP server ที่ทีมเชื่อมได้

server เก็บใน settings 'mcp_servers'. tools ของแต่ละ server จะโผล่ให้ agent
อัตโนมัติในชื่อ mcp__<server>__<tool> (ผ่าน permission gate เหมือน tool อื่น)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.mcp_service import mcp_service
from ..services.settings_store import settings_store

router = APIRouter(prefix="/mcp", tags=["mcp"])


class McpServerRequest(BaseModel):
    name: str
    command: str


@router.get("/servers")
def list_servers() -> dict:
    """status พร้อมจำนวน tools/error ของแต่ละ server (เชื่อมจริงตอนเรียก)"""
    return {"servers": mcp_service.status()}


@router.post("/servers")
def add_server(payload: McpServerRequest) -> dict:
    name = payload.name.strip()
    command = payload.command.strip()
    if not name or not command:
        raise HTTPException(400, "ต้องมีทั้งชื่อและคำสั่ง")
    if "__" in name or any(c.isspace() for c in name):
        raise HTTPException(400, "ชื่อห้ามมีช่องว่างหรือ __ (ใช้ตั้ง namespace ของ tool)")
    servers = list(settings_store.get("mcp_servers") or [])
    if any(s["name"] == name for s in servers):
        raise HTTPException(400, f"มี server ชื่อ {name} อยู่แล้ว")
    servers.append({"name": name, "command": command, "enabled": True})
    settings_store.update({"mcp_servers": servers})
    return {"servers": mcp_service.status()}


@router.delete("/servers/{name}")
def remove_server(name: str) -> dict:
    servers = [s for s in (settings_store.get("mcp_servers") or []) if s["name"] != name]
    settings_store.update({"mcp_servers": servers})
    mcp_service.disconnect(name)
    return {"servers": mcp_service.status()}
