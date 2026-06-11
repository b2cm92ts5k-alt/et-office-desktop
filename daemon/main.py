"""ET Office Daemon — FastAPI app + WebSocket hub (M1-1)

รัน: uvicorn daemon.main:app --port 8797
docs: http://localhost:8797/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

load_dotenv(Path(__file__).parent / ".env")  # โหลดก่อน import modules ที่อ่าน env

from .database import init_db                              # noqa: E402
from .routes import agents, events, logs, roles, settings, system, tasks  # noqa: E402
from .services.ws_manager import ws_manager                # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="ET Office Daemon",
    description="Backend daemon — agent registry, task router (CrewAI), WebSocket hub",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(system.router)
app.include_router(agents.router)
app.include_router(tasks.router)
app.include_router(roles.router)
app.include_router(settings.router)
app.include_router(events.router)
app.include_router(logs.router)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            # client → daemon ไม่มี protocol ใน M1 — รับแล้วทิ้ง (keepalive)
            await ws.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(ws)
