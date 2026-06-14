"""Model Manager routes (M7) — catalog + (ภายหลัง) install/uninstall

M7-2: GET /models/catalog — รายชื่อ local model ที่ติดตั้งได้ + lock ตาม VRAM เครื่อง
install/uninstall (M7-3/M7-4) จะมาเพิ่มใน route นี้
"""
from fastapi import APIRouter

from ..adapters.llm_adapter import VRAMDetector
from ..adapters.model_catalog import get_catalog_with_status

router = APIRouter(prefix="/models", tags=["models"])
_detector = VRAMDetector()


@router.get("/catalog")
def catalog() -> dict:
    """catalog + flag locked (VRAM ไม่ถึง) — UI Settings (M7-5) ใช้ render รายการ + disable ตัวที่ล็อก"""
    vram = _detector.detect()
    return {
        "vram_gb": vram["vram_gb"],
        "recommended_base": vram["recommended"],  # qwen3 base auto (M7-1)
        "models": get_catalog_with_status(vram["vram_gb"]),
    }
