"""LLM Adapter factory — CrewAI LLM ต่อทุก provider (M1-7)

Default = Ollama local (ฟรี 100%) — cloud provider ใช้ API key จาก .env เท่านั้น
key ไม่เคยอยู่ใน agent config / registry / log (privacy rule จาก design doc)
"""
from __future__ import annotations

import os
import subprocess

from crewai import LLM

from ..models.schemas import LLMConfig

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

ENV_KEY_MAP = {
    "claude": "ANTHROPIC_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "openai": "OPENAI_API_KEY",
}

DEFAULT_CLOUD_MODELS = {
    "claude": "claude-sonnet-4-6",
    "gemini": "gemini-2.0-flash",
    "openai": "gpt-4o",
}


class MissingAPIKeyError(Exception):
    pass


def get_llm(cfg: LLMConfig, temperature: float | None = None) -> LLM:
    """temperature ระบุได้สำหรับงานที่ต้อง deterministic (tool loop M6-9 ใช้ 0.2)"""
    extra = {} if temperature is None else {"temperature": temperature}
    if cfg.provider == "ollama":
        return LLM(model=f"ollama/{cfg.model}", base_url=OLLAMA_BASE_URL, **extra)

    env_var = ENV_KEY_MAP[cfg.provider]
    key = os.environ.get(env_var, "")
    if not key:
        raise MissingAPIKeyError(
            f"ยังไม่ได้ตั้ง API key สำหรับ {cfg.provider} — ใส่ได้ที่ Settings (env: {env_var})"
        )

    model = cfg.model or DEFAULT_CLOUD_MODELS[cfg.provider]
    prefix = {"claude": "anthropic", "gemini": "gemini", "openai": "openai"}[cfg.provider]
    return LLM(model=f"{prefix}/{model}", api_key=key, **extra)


class VRAMDetector:
    """ตรวจ VRAM ผ่าน nvidia-smi → แนะนำ base model (qwen3) ตามสเปค (M1-5, ปรับ M7-1)

    base = qwen3 ทั่วไปเท่านั้น (local-first). **ไม่ใช้ qwen3-coder เป็น base** เพราะ Ollama
    มีเล็กสุด 30B (~19GB) เครื่องทั่วไปรันไม่ได้. Gemma + model เฉพาะทาง (coder/math/vl)
    = ผู้ใช้ติดตั้งเพิ่มเองผ่าน Model Manager (M7) ไม่อยู่ใน auto-select.
    tag ที่ใช้มีจริงบน Ollama แล้ว (verified มิ.ย.2026).
    """

    # (lo, hi) VRAM GB → qwen3 tag (recommended เป็น string เดียว)
    # boundary อิงขนาดที่รันได้จริง: 1.7b~1.4GB / 8b~5.2GB / 14b~9.3GB(ต้อง ~12GB) / 32b~20GB(ต้อง ~24GB)
    # การ์ด 8GB → qwen3:8b (พอดี — ตัวที่ daemon รันผ่านจริง), ไม่ดัน 14b ที่ล้น VRAM
    MODEL_MAP = [
        ((0, 6),    "qwen3:1.7b"),
        ((6, 12),   "qwen3:8b"),
        ((12, 24),  "qwen3:14b"),
        ((24, 999), "qwen3:32b"),
    ]

    def detect(self) -> dict:
        vram_gb = self._read_vram_gb()
        model = self.MODEL_MAP[-1][1]
        for (lo, hi), tag in self.MODEL_MAP:
            if lo <= vram_gb < hi:
                model = tag
                break
        return {"vram_gb": round(vram_gb, 1), "recommended": model}

    def _read_vram_gb(self) -> float:
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, timeout=10,
            )
            if result.returncode == 0:
                return int(result.stdout.decode().strip().splitlines()[0]) / 1024
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            pass
        return 4.0  # ไม่มี NVIDIA GPU → สมมติ 4GB (CPU/iGPU ใช้ model เล็ก)


def ollama_ok() -> bool:
    """เช็คว่า Ollama server ตอบไหม (ใช้ใน /health)"""
    import urllib.request
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/version", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def ollama_list_installed() -> list[str]:
    """รายชื่อ model ที่ pull ไว้แล้ว (GET /api/tags) — ใช้เติม flag installed ใน catalog (M7-3)"""
    import json
    import urllib.request
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/tags", timeout=5) as r:
            data = json.loads(r.read().decode())
        return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return []


def ollama_ps_running() -> list[str]:
    """model ที่กำลัง load อยู่ใน VRAM ตอนนี้ (GET /api/ps) — ใช้กฎ 'ห้ามลงตอนมีตัวอื่นรัน' (M7-3)"""
    import json
    import urllib.request
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/ps", timeout=5) as r:
            data = json.loads(r.read().decode())
        return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return []


def ollama_pull_stream(tag: str):
    """generator: stream progress ของ ollama pull (POST /api/pull) ทีละบรรทัด JSON
    yield dict เช่น {"status":"pulling ...","total":N,"completed":M} จนจบ {"status":"success"}
    """
    import json
    import urllib.request
    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/pull",
        data=json.dumps({"model": tag, "stream": True}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        for raw in r:
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw.decode())
            except json.JSONDecodeError:
                continue


def ollama_delete(tag: str) -> bool:
    """ลบ model (DELETE /api/delete) — ใช้ใน M7-4 uninstall"""
    import json
    import urllib.request
    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/delete",
        data=json.dumps({"model": tag}).encode(),
        headers={"Content-Type": "application/json"},
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200
    except Exception:
        return False
