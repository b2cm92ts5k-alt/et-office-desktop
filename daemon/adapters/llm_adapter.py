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


def get_llm(cfg: LLMConfig) -> LLM:
    if cfg.provider == "ollama":
        return LLM(model=f"ollama/{cfg.model}", base_url=OLLAMA_BASE_URL)

    env_var = ENV_KEY_MAP[cfg.provider]
    key = os.environ.get(env_var, "")
    if not key:
        raise MissingAPIKeyError(
            f"ยังไม่ได้ตั้ง API key สำหรับ {cfg.provider} — ใส่ได้ที่ Settings (env: {env_var})"
        )

    model = cfg.model or DEFAULT_CLOUD_MODELS[cfg.provider]
    prefix = {"claude": "anthropic", "gemini": "gemini", "openai": "openai"}[cfg.provider]
    return LLM(model=f"{prefix}/{model}", api_key=key)


class VRAMDetector:
    """ตรวจ VRAM ผ่าน nvidia-smi → แนะนำ model ที่เหมาะ (M1-5)
    หมายเหตุ: ใช้ tag ที่มีจริงบน Ollama (blueprint เขียน qwen3:7b/gemma4 ซึ่งไม่มีจริง)
    """

    MODEL_MAP = [
        ((0, 4),    {"qwen": "qwen2.5:1.5b", "gemma": "gemma3:1b"}),
        ((4, 8),    {"qwen": "qwen3:8b",     "gemma": "gemma3:4b"}),
        ((8, 16),   {"qwen": "qwen3:8b",     "gemma": "gemma3:12b"}),
        ((16, 999), {"qwen": "qwen3:32b",    "gemma": "gemma3:27b"}),
    ]

    def detect(self) -> dict:
        vram_gb = self._read_vram_gb()
        for (lo, hi), models in self.MODEL_MAP:
            if lo <= vram_gb < hi:
                return {"vram_gb": round(vram_gb, 1), "recommended": models}
        return {"vram_gb": round(vram_gb, 1), "recommended": self.MODEL_MAP[-1][1]}

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
