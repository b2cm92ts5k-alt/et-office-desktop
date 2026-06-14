"""Model Manager routes (M7) — catalog + install

M7-2: GET /models/catalog — รายชื่อ local model ที่ติดตั้งได้ + lock ตาม VRAM เครื่อง
M7-3: POST /models/install — ollama pull (background) + progress ผ่าน WS event
      กฎ: ติดตั้งได้ครั้งละ 1 ตัว, ห้ามลงตอนมี local model อื่นรันอยู่, VRAM ต้องถึง
uninstall (M7-4) จะมาเพิ่มใน route นี้
"""
from __future__ import annotations

import asyncio
import os
import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..adapters import model_catalog
from ..adapters.llm_adapter import (
    DEFAULT_CLOUD_MODELS,
    ENV_KEY_MAP,
    VRAMDetector,
    ollama_delete,
    ollama_list_installed,
    ollama_ps_running,
    ollama_pull_stream,
)
from ..services.settings_store import settings_store
from ..services.ws_manager import ws_manager

router = APIRouter(prefix="/models", tags=["models"])
_detector = VRAMDetector()

# install ทีละ 1 ตัวเท่านั้น (กันยิงซ้อน + กันเครื่องรับไม่ไหว)
_install_lock = threading.Lock()
_installing_tag: str | None = None


class InstallReq(BaseModel):
    tag: str


@router.get("/catalog")
def catalog() -> dict:
    """catalog + flag locked (VRAM ไม่ถึง) / installed (มีบน ollama) / app_installed (ลงผ่านแอป → uninstall ได้)"""
    vram = _detector.detect()
    on_ollama = set(ollama_list_installed())
    app_installed = set(settings_store.get("installed_models") or [])
    models = model_catalog.get_catalog_with_status(vram["vram_gb"], on_ollama)
    for m in models:
        m["app_installed"] = m["tag"] in app_installed
    return {
        "vram_gb": vram["vram_gb"],
        "recommended_base": vram["recommended"],  # qwen3 base auto (M7-1)
        "installing": _installing_tag,            # tag ที่กำลังลง (None = ว่าง) — UI disable ปุ่ม + resume progress
        "models": models,
    }


@router.get("/available")
def available() -> dict:
    """model ที่เลือกได้ตอนสร้าง/แก้ agent (M7-6): qwen3 base เสมอ + local ที่ลง + cloud ที่มี key
    ใช้ร่วมกันทั้ง HIRE dialog, gear ของ agent, และ CEO onboarding (M8)
    """
    base = _detector.detect()["recommended"]
    local = ollama_list_installed() or [base]  # ออฟไลน์/ยังไม่ pull → fallback base
    opts: list[dict] = []
    for tag in local:
        is_base = tag == base
        opts.append({
            "provider": "ollama",
            "model": tag,
            "label": f"{tag} (local)" + (" • default" if is_base else ""),
            "recommended": is_base,
        })
    for prov, env in ENV_KEY_MAP.items():
        if os.environ.get(env):  # มี API key เท่านั้นถึงโผล่ให้เลือก
            m = DEFAULT_CLOUD_MODELS[prov]
            opts.append({"provider": prov, "model": m, "label": f"☁ {prov} ({m})", "recommended": False})
    return {"options": opts, "recommended_base": base}


@router.post("/install")
async def install(req: InstallReq) -> dict:
    """ตรวจกฎทั้งหมดก่อน แล้วลงใน background thread + broadcast progress ผ่าน WS
    consent ผู้ใช้ทำที่ UI (M7-5) ก่อนเรียก endpoint นี้
    """
    global _installing_tag
    tag = req.tag
    entry = model_catalog.get(tag)
    if not entry:
        raise HTTPException(400, "ไม่รู้จัก model นี้ในแคตตาล็อก")

    vram = _detector.detect()["vram_gb"]
    if vram < entry["min_vram_gb"]:
        raise HTTPException(400, f"VRAM ไม่พอ: {entry['name']} ต้องการ ~{entry['min_vram_gb']}GB (เครื่องมี {vram}GB)")

    with _install_lock:
        if _installing_tag:
            raise HTTPException(409, f"กำลังติดตั้ง {_installing_tag} อยู่ — รอให้เสร็จก่อน")
        if tag in (settings_store.get("installed_models") or []) or tag in ollama_list_installed():
            raise HTTPException(400, f"{entry['name']} ติดตั้งไว้แล้ว")
        app_installed = list(settings_store.get("installed_models") or [])
        if app_installed:
            raise HTTPException(400, f"ติดตั้งได้ครั้งละ 1 ตัว — uninstall {app_installed[0]} ก่อน")
        running = [r for r in ollama_ps_running() if r]
        if running:
            raise HTTPException(400, "มี local model กำลังรันอยู่: " + ", ".join(running) + " — ปิด/รอให้ unload ก่อนติดตั้ง")
        _installing_tag = tag  # จองคิวก่อนปล่อย lock

    loop = asyncio.get_running_loop()
    threading.Thread(target=_pull_worker, args=(loop, tag), daemon=True).start()
    return {"accepted": True, "tag": tag}


@router.post("/uninstall")
async def uninstall(req: InstallReq) -> dict:
    """ลบ model — เฉพาะตัวที่ลงผ่านแอป (track ใน installed_models) เท่านั้น (M7-4)
    กัน user เผลอลบ base qwen3 หรือ model ที่ user pull เองนอกแอป
    """
    tag = req.tag
    app_installed = list(settings_store.get("installed_models") or [])
    if tag not in app_installed:
        raise HTTPException(400, "ลบได้เฉพาะ model ที่ติดตั้งผ่านแอปเท่านั้น")
    if _installing_tag:
        raise HTTPException(409, f"กำลังติดตั้ง {_installing_tag} อยู่ — รอให้เสร็จก่อน")
    if not ollama_delete(tag):
        raise HTTPException(502, f"ลบไม่สำเร็จ — Ollama อาจไม่ได้รันอยู่ ({tag})")
    settings_store.update({"installed_models": [t for t in app_installed if t != tag]})
    await ws_manager.broadcast({"type": "model.uninstall.done", "data": {"tag": tag}})
    return {"removed": tag}


def _pull_worker(loop: asyncio.AbstractEventLoop, tag: str) -> None:
    """รัน ollama pull, broadcast model.install.progress/done/error, บันทึก installed_models เมื่อสำเร็จ"""
    global _installing_tag

    def emit(etype: str, data: dict) -> None:
        ws_manager.broadcast_threadsafe(loop, {"type": etype, "data": data})

    last_status = ""
    last_bucket = -1
    try:
        for p in ollama_pull_stream(tag):
            status = p.get("status", "")
            total, completed = p.get("total"), p.get("completed")
            # บาง progress line มี total แต่ยังไม่มี completed (หรือกลับกัน) — กัน None/int
            pct = int(completed / total * 100) if (total and completed is not None) else None
            # broadcast เมื่อ status เปลี่ยน หรือ % ขยับทุก 5 ก้าว (กัน spam WS/journal)
            if pct is not None:
                bucket = pct // 5
                if bucket != last_bucket or status != last_status:
                    last_bucket, last_status = bucket, status
                    emit("model.install.progress", {"tag": tag, "status": status, "percent": pct})
            elif status != last_status:
                last_status = status
                emit("model.install.progress", {"tag": tag, "status": status})

        installed = list(settings_store.get("installed_models") or [])
        if tag not in installed:
            installed.append(tag)
            settings_store.update({"installed_models": installed})
        emit("model.install.done", {"tag": tag})
    except Exception as e:  # noqa: BLE001
        emit("model.install.error", {"tag": tag, "error": str(e)[:200]})
    finally:
        with _install_lock:
            _installing_tag = None
