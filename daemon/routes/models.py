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
    active_local_tag,
    ollama_delete,
    ollama_list_installed,
    ollama_pull_stream,
    ollama_unload,
)
from ..services.agent_registry import registry
from ..services.settings_store import settings_store
from ..services.ws_manager import ws_manager

router = APIRouter(prefix="/models", tags=["models"])
_detector = VRAMDetector()

# สถานะที่ถือว่า "ทีมกำลังทำงาน" — ห้ามสลับ local model ตอนนี้ (กัน crew ที่รันอยู่หลุดกลางคัน)
_BUSY_STATUSES = {"working", "thinking", "collab"}


def _team_busy() -> bool:
    return any(a.status in _BUSY_STATUSES for a in registry.all())

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
        "active_local_model": active_local_tag(), # tag เดียวที่ทุก agent ใช้จริง (M7-8)
        "installing": _installing_tag,            # tag ที่กำลังลง (None = ว่าง) — UI disable ปุ่ม + resume progress
        "team_busy": _team_busy(),                # ทีมกำลังทำงาน → UI disable การสลับ
        "models": models,
    }


@router.get("/available")
def available() -> dict:
    """model ที่เลือกได้ตอนสร้าง/แก้ agent (M7-6): local ตัวเดียว (active) + cloud ที่มี key
    ใช้ร่วมกันทั้ง HIRE dialog, gear ของ agent, และ CEO onboarding (M8)

    M7-8: local เหลือ "ตัวเดียว" = active_local_model เท่านั้น — ทุก agent ใช้ตัวเดียวกัน
    จึงไม่มีทางเลือก local หลายตัวให้ผสมจน Ollama โหลดซ้อนกัน. อยากใช้ตัวอื่น = สลับ
    active ผ่าน Model Manager (เด้งยกทีม). งานเฉพาะทางที่ต้องแยก → ใช้ cloud (มี API key)
    """
    active = active_local_tag()
    opts: list[dict] = [{
        "provider": "ollama",
        "model": active,
        "label": f"{active} (local • ใช้ร่วมทั้งทีม)",
        "recommended": True,
    }]
    for prov, env in ENV_KEY_MAP.items():
        if os.environ.get(env):  # มี API key เท่านั้นถึงโผล่ให้เลือก
            m = DEFAULT_CLOUD_MODELS[prov]
            opts.append({"provider": prov, "model": m, "label": f"☁ {prov} ({m})", "recommended": False})
    return {"options": opts, "recommended_base": active}


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
    # resident ทีละ 1 ตัวเสมอ (active เด่ียว) → เช็ก VRAM ของตัวใหม่ตัวเดียวพอ ไม่ต้องบวก base
    if vram < entry["min_vram_gb"]:
        raise HTTPException(400, f"VRAM ไม่พอ: {entry['name']} ต้องการ ~{entry['min_vram_gb']}GB (เครื่องมี {vram}GB)")

    # สลับ active = ทุก agent เด้งไปใช้ตัวใหม่ → ห้ามทำตอน crew กำลังรัน (จะหลุดกลางคัน)
    if _team_busy():
        raise HTTPException(409, "ทีมกำลังทำงานอยู่ — รอให้ทีมว่างก่อนค่อยสลับ local model")

    with _install_lock:
        if _installing_tag:
            raise HTTPException(409, f"กำลังติดตั้ง {_installing_tag} อยู่ — รอให้เสร็จก่อน")
        if tag in (settings_store.get("installed_models") or []) or tag in ollama_list_installed():
            raise HTTPException(400, f"{entry['name']} ติดตั้งไว้แล้ว")
        app_installed = list(settings_store.get("installed_models") or [])
        if app_installed:
            raise HTTPException(400, f"ใช้ local model เพิ่มได้ครั้งละ 1 ตัว — ลบ {app_installed[0]} ก่อน (จะกลับไปใช้ qwen3 default)")
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
    # ลบ active = ทุก agent เด้งกลับไป qwen3 default → ห้ามทำตอนทีมทำงาน
    if _team_busy():
        raise HTTPException(409, "ทีมกำลังทำงานอยู่ — รอให้ทีมว่างก่อนค่อยลบ/สลับ local model")
    if not ollama_delete(tag):
        raise HTTPException(502, f"ลบไม่สำเร็จ — Ollama อาจไม่ได้รันอยู่ ({tag})")
    changes: dict = {"installed_models": [t for t in app_installed if t != tag]}
    # ตัวที่ลบคือ active อยู่ → เคลียร์ active กลับไปใช้ qwen3 default (VRAMDetector)
    if (settings_store.get("active_local_model") or "") == tag:
        changes["active_local_model"] = ""
    settings_store.update(changes)
    new_active = active_local_tag()
    await ws_manager.broadcast({"type": "model.uninstall.done", "data": {"tag": tag, "active": new_active}})
    return {"removed": tag, "active": new_active}


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

        # สลับ active มาที่ตัวใหม่ → ทุก ollama agent เด้งมาใช้ตัวนี้ (chokepoint get_llm)
        prev_active = active_local_tag()
        installed = list(settings_store.get("installed_models") or [])
        if tag not in installed:
            installed.append(tag)
        settings_store.update({"installed_models": installed, "active_local_model": tag})
        # ปลดตัวเก่า (qwen3 default) ออกจาก VRAM ทันที — กัน resident 2 ตัวช่วงสลับ
        if prev_active and prev_active != tag:
            ollama_unload(prev_active)
        emit("model.install.done", {"tag": tag, "active": tag, "prev": prev_active,
                                     "restart_hint": True})
    except Exception as e:  # noqa: BLE001
        emit("model.install.error", {"tag": tag, "error": str(e)[:200]})
    finally:
        with _install_lock:
            _installing_tag = None
