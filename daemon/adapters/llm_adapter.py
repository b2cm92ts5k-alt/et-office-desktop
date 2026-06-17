"""LLM Adapter factory — CrewAI LLM ต่อทุก provider (M1-7)

Default = Ollama local (ฟรี 100%) — cloud provider ใช้ API key จาก .env เท่านั้น
key ไม่เคยอยู่ใน agent config / registry / log (privacy rule จาก design doc)
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
from collections import OrderedDict

from crewai import LLM

from ..models.schemas import LLMConfig

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

# --- LLM response cache (M11-4, §3.6) ---
# งานซ้ำ ๆ (เช่น commit message สั้น) ไม่ต้องยิง model ใหม่ — key = hash(model+messages+temp+schema)
# creative (temp > CACHE_TEMP_MAX) ข้าม cache เพราะอยากได้คำตอบหลากหลาย
CACHE_MAX = 100          # LRU entries
CACHE_TTL = 600          # วินาที (10 นาที)
CACHE_TEMP_MAX = 0.5     # temp เกินนี้ = creative → ไม่ cache
_cache: "OrderedDict[str, tuple[float, str]]" = OrderedDict()
_cache_lock = threading.Lock()


def _cache_key(model: str, messages: list[dict], temperature: float, schema: dict | None) -> str:
    blob = json.dumps(
        {"m": model, "msgs": messages, "t": temperature, "s": schema},
        ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> str | None:
    with _cache_lock:
        item = _cache.get(key)
        if item is None:
            return None
        ts, val = item
        if time.time() - ts > CACHE_TTL:
            _cache.pop(key, None)  # หมดอายุ
            return None
        _cache.move_to_end(key)    # LRU touch
        return val


def _cache_put(key: str, val: str) -> None:
    with _cache_lock:
        _cache[key] = (time.time(), val)
        _cache.move_to_end(key)
        while len(_cache) > CACHE_MAX:
            _cache.popitem(last=False)  # ทิ้งตัวเก่าสุด


def cache_clear() -> None:
    """ล้าง cache ทั้งหมด (ใช้ตอนสลับ active model / เทส)"""
    with _cache_lock:
        _cache.clear()

ENV_KEY_MAP = {
    "claude": "ANTHROPIC_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "openai": "OPENAI_API_KEY",
}

DEFAULT_CLOUD_MODELS = {
    "claude": "claude-sonnet-4-6",
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o",
}


class MissingAPIKeyError(Exception):
    pass


# M11-9 (§4.1/5.1) — specialist cloud แนะนำต่อ role (opt-in: โชว์ banner เมื่อมี key, CEO กดเอง ไม่บังคับ)
# cloud ไม่กิน VRAM → ไม่ละเมิด 1-active-local; default ทุก agent ยังเป็น local qwen3
SPECIALIST_PRESETS: list[dict] = [
    {"match": ["producer", "orchestrat", "วางแผน", "manager", "เลขา"],
     "provider": "claude", "model": "claude-sonnet-4-6", "reason": "วางแผน/แตกงานหลายขั้น แม่นสุด"},
    {"match": ["coder", "program", "dev", "เขียนโค้ด", "โปรแกรม", "วิศวกร"],
     "provider": "claude", "model": "claude-sonnet-4-6", "reason": "code quality สูงสุด"},
    {"match": ["design", "ดีไซน์", "ออกแบบ", "ศิลป", "กราฟิก"],
     "provider": "openai", "model": "gpt-4o", "reason": "multimodal รับภาพได้"},
    {"match": ["research", "วิจัย", "ค้นคว้า", "หาข้อมูล", "วิเคราะห์"],
     "provider": "gemini", "model": "gemini-2.5-flash", "reason": "ถูก+เร็ว web grounding ดี"},
]


# M11-13 (#141) — catalog cloud model ต่อ provider: 1 key เลือกได้หลายตัว (ไม่ฟิก)
# tier: "free" (Google free tier) / "paid" (in/out = USD ต่อ 1M token) — ป้อน cost_guard per-model
# หมายเหตุ: model id อ้างชื่อจากภาพ CEO (มิ.ย.2026) — gemini-2.5-flash ยืนยันใช้ได้จริง,
# ตัวอื่นปรับ id ให้ตรง API ปัจจุบันได้ที่นี่ที่เดียว (CEO แก้ catalog ได้)
CLOUD_CATALOG: dict[str, list[dict]] = {
    "gemini": [
        {"model": "gemini-2.5-pro",         "label": "Gemini 2.5 Pro",         "tier": "free", "in": 0, "out": 0},
        {"model": "gemini-3-flash",         "label": "Gemini 3 Flash",         "tier": "free", "in": 0, "out": 0},
        {"model": "gemini-2.5-flash",       "label": "Gemini 2.5 Flash",       "tier": "free", "in": 0, "out": 0},
        {"model": "gemini-2.5-flash-lite",  "label": "Gemini 2.5 Flash-Lite",  "tier": "free", "in": 0, "out": 0},
        {"model": "gemini-3.1-flash-lite",  "label": "Gemini 3.1 Flash-Lite",  "tier": "free", "in": 0, "out": 0},
    ],
    "claude": [
        {"model": "claude-opus-4-8",   "label": "Claude Opus 4.8",   "tier": "paid", "in": 5, "out": 25},
        {"model": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6", "tier": "paid", "in": 3, "out": 15},
        {"model": "claude-haiku-4-5",  "label": "Claude Haiku 4.5",  "tier": "paid", "in": 1, "out": 5},
    ],
    "openai": [
        {"model": "gpt-5.5",      "label": "GPT-5.5",      "tier": "paid", "in": 5,   "out": 30},
        {"model": "gpt-5.5-pro",  "label": "GPT-5.5 Pro",  "tier": "paid", "in": 30,  "out": 180},
        {"model": "gpt-5.4",      "label": "GPT-5.4",      "tier": "paid", "in": 2.5, "out": 15},
        {"model": "gpt-5.4-mini", "label": "GPT-5.4 Mini", "tier": "paid", "in": 0.75, "out": 4.5},
        {"model": "gpt-5.4-nano", "label": "GPT-5.4 Nano", "tier": "paid", "in": 0.2, "out": 1.25},
        {"model": "o3",           "label": "o3",           "tier": "paid", "in": 2,   "out": 8},
        {"model": "o3-mini",      "label": "o3-mini",      "tier": "paid", "in": 1,   "out": 4},
        {"model": "o1",           "label": "o1",           "tier": "paid", "in": 15,  "out": 60},
        {"model": "o1-pro",       "label": "o1-Pro",       "tier": "paid", "in": 150, "out": 180},
    ],
}


def cloud_models(provider: str) -> list[dict]:
    """รายชื่อ cloud model ของ provider (M11-13) — ว่าง = provider นั้นไม่มี catalog"""
    return CLOUD_CATALOG.get(provider, [])


def cloud_price(provider: str, model: str) -> tuple[float, float] | None:
    """ราคา (in, out) USD/1M token ของ model จาก catalog — None ถ้าไม่อยู่ใน catalog (M11-13)"""
    for m in CLOUD_CATALOG.get(provider, []):
        if m["model"] == model:
            return (float(m["in"]), float(m["out"]))
    return None


def specialist_for(role: str = "", keywords: list[str] | None = None) -> dict | None:
    """หา specialist cloud ที่เหมาะกับ role (M11-9) — คืน {provider, model, reason} หรือ None

    match จาก role + keywords (ไม่สน case). ใช้โชว์ banner ตอน hire/gear — ไม่เปลี่ยน model เอง.
    """
    hay = (role + " " + " ".join(keywords or [])).lower()
    for p in SPECIALIST_PRESETS:
        if any(kw in hay for kw in p["match"]):
            return {"provider": p["provider"], "model": p["model"], "reason": p["reason"]}
    return None


def available_cloud_providers() -> dict:
    """provider ไหนมี API key พร้อมใช้ (M11-9) — ใช้ตัดสินว่าจะโชว์ banner ไหม"""
    return {prov: bool(os.environ.get(env)) for prov, env in ENV_KEY_MAP.items()}


def active_local_tag() -> str:
    """local tag เดียวที่ทุก ollama agent ต้องใช้ (M7-8) — กันโหลด 2 ตัวพร้อมกัน

    ที่มา: settings active_local_model (ผู้ใช้สลับผ่าน Model Manager) → ถ้าว่าง
    fallback = VRAMDetector recommended (qwen3 base ตาม VRAM). เป็น single source
    of truth: agent ตั้ง model อะไรไว้ก็ถูก coerce มาที่ตัวนี้ตอน get_llm.
    import settings_store แบบ lazy กัน circular import (settings_store ไม่ดึง adapter).
    """
    from ..services.settings_store import settings_store
    tag = (settings_store.get("active_local_model") or "").strip()
    return tag or VRAMDetector().detect()["recommended"]


def get_llm(cfg: LLMConfig, temperature: float | None = None) -> LLM:
    """temperature ระบุได้สำหรับงานที่ต้อง deterministic (tool loop M6-9 ใช้ 0.2)"""
    extra = {} if temperature is None else {"temperature": temperature}
    if cfg.provider == "ollama":
        # บังคับใช้ active tag เดียวเสมอ (ไม่สน cfg.model) — invariant กันรัน local 2 ตัวซ้อน (M7-8)
        return LLM(model=f"ollama/{active_local_tag()}", base_url=OLLAMA_BASE_URL, **extra)

    env_var = ENV_KEY_MAP[cfg.provider]
    key = os.environ.get(env_var, "")
    if not key:
        raise MissingAPIKeyError(
            f"ยังไม่ได้ตั้ง API key สำหรับ {cfg.provider} — ใส่ได้ที่ Settings (env: {env_var})"
        )

    model = cfg.model or DEFAULT_CLOUD_MODELS[cfg.provider]
    prefix = {"claude": "anthropic", "gemini": "gemini", "openai": "openai"}[cfg.provider]
    return LLM(model=f"{prefix}/{model}", api_key=key, **extra)


def ollama_chat(
    messages: list[dict],
    *,
    schema: dict | None = None,
    temperature: float = 0.2,
    timeout: int = 180,
    stats: dict | None = None,
    think: bool | None = None,
) -> str:
    """เรียก Ollama /api/chat ตรง ๆ พร้อมบังคับ output ตาม JSON schema (M11-1, §3.1)

    ใช้กับ local tool-loop เท่านั้น — `format: <schema>` ของ Ollama 0.5+ การันตี output
    เป็น JSON ที่ตรง schema 100% (qwen3 หลุด schema บ่อยถ้าบังคับผ่าน prompt อย่างเดียว).
    บังคับ model = active_local_tag() เสมอ (เคารพกฎ 1-active-local M7-8 เหมือน get_llm).
    cloud provider ไม่ผ่านทางนี้ — ยังใช้ CrewAI LLM (มี structured output ของตัวเอง).
    cache (M11-4): temp <= CACHE_TEMP_MAX → ใช้ cache ตาม (model+messages+temp+schema+think).
    stats (M11-5): ถ้าส่ง dict มา → สะสม tokens_in/tokens_out/llm_calls (cache hit = 0 token).
    think (M11-8): True=/think (วางแผน), False=/no_think (เร็ว); None=ปล่อยตาม default ของ model.
    """
    import urllib.request
    model = active_local_tag()
    if stats is not None:
        stats["model"] = model
        stats["provider"] = "ollama"
    use_cache = temperature <= CACHE_TEMP_MAX
    key = _cache_key(model, messages, temperature, (schema, think)) if use_cache else ""
    if key:
        hit = _cache_get(key)
        if hit is not None:
            if stats is not None:
                stats["cache_hits"] = stats.get("cache_hits", 0) + 1
            return hit
    body: dict = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if schema is not None:
        body["format"] = schema
    if think is not None:
        body["think"] = think   # qwen3: True=/think, False=/no_think (M11-8)
    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    content = data.get("message", {}).get("content", "")
    if stats is not None:
        stats["tokens_in"] = stats.get("tokens_in", 0) + int(data.get("prompt_eval_count", 0) or 0)
        stats["tokens_out"] = stats.get("tokens_out", 0) + int(data.get("eval_count", 0) or 0)
        stats["llm_calls"] = stats.get("llm_calls", 0) + 1
    if key and content:
        _cache_put(key, content)
    return content


# M11-6 (§3.4) — context budget ต่อขนาด model (scale ตาม VRAM: เครื่องแรง = หน้าต่างกว้าง = AI ฉลาดกว่า)
# keep_turns = จำนวน message ท้ายสุดที่เก็บเต็ม | obs_clip = ตัด observation ที่ส่งกลับ model
# sys_budget_tok = เพดาน token ของ system prompt+schema (แค่เตือน ไม่ตัด เพราะ tool list ห้ามหาย)
CONTEXT_PRESETS: dict[str, dict] = {
    "qwen3:1.7b": {"keep_turns": 6,  "obs_clip": 2000,  "sys_budget_tok": 1500},
    "qwen3:8b":   {"keep_turns": 8,  "obs_clip": 4000,  "sys_budget_tok": 2000},
    "qwen3:14b":  {"keep_turns": 12, "obs_clip": 8000,  "sys_budget_tok": 3000},
    "qwen3:32b":  {"keep_turns": 16, "obs_clip": 16000, "sys_budget_tok": 4000},
}
_CONTEXT_DEFAULT = {"keep_turns": 8,  "obs_clip": 4000,  "sys_budget_tok": 2000}
_CONTEXT_CLOUD = {"keep_turns": 20, "obs_clip": 16000, "sys_budget_tok": 6000}


def context_budget(provider: str = "ollama") -> dict:
    """งบ context ต่อ hop (M11-6) — local อิงขนาด active model จริง, cloud ใช้ preset กว้าง

    เครื่องที่ VRAM มาก → active model ใหญ่ → keep_turns/obs_clip มากขึ้นอัตโนมัติ
    (model ที่ลงไม่ตรง preset เช่น gemma → ใช้ default ของ 8b เป็นค่ากลางปลอดภัย).
    """
    if provider != "ollama":
        return dict(_CONTEXT_CLOUD)
    return dict(CONTEXT_PRESETS.get(active_local_tag(), _CONTEXT_DEFAULT))


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


def ollama_unload(tag: str) -> bool:
    """ปลด model ออกจาก VRAM ทันที (POST /api/generate keep_alive:0) — ใช้ตอนสลับ active
    model (M7-8) ให้ตัวเก่าคืน VRAM ก่อนตัวใหม่โหลด ไม่ลบไฟล์บนดิสก์
    """
    import json
    import urllib.request
    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=json.dumps({"model": tag, "keep_alive": 0}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception:
        return False
