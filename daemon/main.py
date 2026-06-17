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
from .routes import agents, events, files, logs, mcp, models, permissions, proposals, roles, settings, sprites, system, tasks  # noqa: E402
from .services.permission_gate import permission_gate      # noqa: E402
from .services.social_service import social_service        # noqa: E402
from .services.ws_manager import ws_manager                # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    import asyncio
    permission_gate.attach_loop(asyncio.get_running_loop())  # broadcast จาก task thread (M6-8)
    social_service.start()  # idle social loop (M3-9)
    yield
    social_service.stop()
    from .services.mcp_service import mcp_service  # ปิด MCP subprocess ที่ค้าง (M10)
    mcp_service.stop_all()


app = FastAPI(
    title="ET Office Daemon",
    description="Backend daemon — agent registry, task router (CrewAI), WebSocket hub",
    version="0.1.0",
    lifespan=lifespan,
)

# sidebar (pywebview) โหลดจาก file:// → origin "null" — ต้องเปิด CORS ไม่งั้น fetch โดนบล็อก
# daemon ฟังแค่ localhost จึงเปิดกว้างได้โดยไม่เสีย privacy posture
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _no_cache_sidebar(request, call_next):
    """กัน WebView2 cache หน้า/สคริปต์ sidebar ค้างเวลาแก้โค้ด — โหลดใหม่ทุก restart"""
    resp = await call_next(request)
    if request.url.path.startswith("/sidebar"):
        resp.headers["Cache-Control"] = "no-store"
    return resp

app.include_router(system.router)
app.include_router(models.router)
app.include_router(files.router)
app.include_router(mcp.router)
app.include_router(agents.router)
app.include_router(tasks.router)
app.include_router(roles.router)
app.include_router(settings.router)
app.include_router(events.router)
app.include_router(logs.router)
app.include_router(proposals.router)
app.include_router(sprites.router)
app.include_router(permissions.router)

from fastapi import Response  # noqa: E402


@app.get("/favicon.ico", include_in_schema=False)
def _favicon() -> Response:
    """กัน 404 สีแดงใน log — webview/บราวเซอร์ขอ favicon อัตโนมัติ (ไม่มีไอคอนก็ไม่เป็นไร)"""
    return Response(status_code=204)


from fastapi.staticfiles import StaticFiles  # noqa: E402

# serve หน้า sidebar (same-origin — fetch/WS ไม่ติด CORS/file:// ของ webview)
_SIDEBAR_WEB = Path(__file__).parent.parent / "sidebar" / "web"
if _SIDEBAR_WEB.is_dir():
    app.mount("/sidebar", StaticFiles(directory=_SIDEBAR_WEB, html=True), name="sidebar")

# custom spritesheets ที่ user อัพโหลด (M6-2 v2) — Godot โหลดจากที่นี่
app.mount("/sprites/files", StaticFiles(directory=sprites.SPRITES_DIR), name="sprites")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            # client → daemon ไม่มี protocol ใน M1 — รับแล้วทิ้ง (keepalive)
            await ws.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(ws)
