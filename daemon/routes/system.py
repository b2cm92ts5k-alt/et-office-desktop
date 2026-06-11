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


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "agents": len(registry.all()),
        "ws_clients": ws_manager.client_count,
        "ollama_ok": ollama_ok(),
    }
