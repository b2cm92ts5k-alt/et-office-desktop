"""/system/vram + /health (M1-5)"""
from fastapi import APIRouter

from ..adapters.llm_adapter import VRAMDetector, ollama_ok
from ..services.agent_registry import registry
from ..services.ws_manager import ws_manager

router = APIRouter(tags=["system"])
_detector = VRAMDetector()


@router.get("/system/vram")
def vram() -> dict:
    return _detector.detect()


@router.get("/tools")
def tools() -> dict:
    """รายชื่อ built-in tool ทั้งหมด (M11-3) — UI ใช้ทำ whitelist checklist ต่อ agent"""
    from ..services.tool_executor import TOOLS_SPEC
    return {"tools": [{"name": n, "desc": s["desc"]} for n, s in TOOLS_SPEC.items()]}


@router.post("/system/shutdown")
def shutdown() -> dict:
    """M12-2 — ปิด daemon นุ่มนวล (sidebar/terminal เรียก) → launcher watch เก็บกวาด godot+sidebar ต่อ

    raise SIGINT ใส่ตัวเอง = uvicorn ปิด graceful (เหมือน Ctrl+C). ตอบ response ก่อนแล้วค่อยปิด.
    """
    import os
    import signal
    import threading
    import time as _t

    def _stop() -> None:
        _t.sleep(0.4)  # ให้ response ส่งถึง client ก่อน
        try:
            signal.raise_signal(signal.SIGINT)
        except Exception:  # noqa: BLE001
            os._exit(0)

    threading.Thread(target=_stop, daemon=True).start()
    return {"shutting_down": True}


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "agents": len(registry.all()),
        "ws_clients": ws_manager.client_count,
        "ollama_ok": ollama_ok(),
    }
