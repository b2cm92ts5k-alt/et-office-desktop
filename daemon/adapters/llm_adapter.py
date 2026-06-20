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

# ─────────────────────────────────────────────────────────────────────────────
# M16-1 — Provider Registry: ทุกอย่างของ 1 cloud provider อยู่ที่เดียว (ยุบ 5 dict เดิม:
# ENV_KEY_MAP / DEFAULT_CLOUD_MODELS / LLM_PREFIX / CLOUD_BASE_URL / _VALIDATE_EP).
# เพิ่ม provider ใหม่ = เพิ่ม 1 entry ที่นี่ที่เดียว (เดิมต้องแก้ 5 ที่กระจาย ลืมง่าย).
#
# fields:
#   label         ชื่อโชว์ UI
#   env_key       ชื่อ ENV ที่เก็บ key default (.env)
#   default_model model ที่ใช้เมื่อ agent ไม่ระบุ
#   route         วิธียิงผ่าน CrewAI LLM:
#                   {"kind":"litellm","prefix":"anthropic"}  → LLM("anthropic/<model>")
#                   {"kind":"openai_compat","base_url":...}  → LLM("<model>", base_url=...) (OpenAI-compatible)
#                   openai_compat ใส่ "extra_headers" เพิ่มได้ (เช่น OpenRouter ต้องการ HTTP-Referer)
#   list          endpoint ดึงรายชื่อ model จริงของ key:
#                   {"url": "...{k}...", "headers": lambda k: {...}}  (M16-2 จะเพิ่ม "parse" ต่อ provider)
PROVIDERS: dict[str, dict] = {
    "claude": {
        "label": "Claude (Anthropic)",
        "env_key": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-6",
        "route": {"kind": "litellm", "prefix": "anthropic"},
        "list": {"url": "https://api.anthropic.com/v1/models",
                 "headers": lambda k: {"x-api-key": k, "anthropic-version": "2023-06-01"}},
    },
    "gemini": {
        "label": "Google Gemini",
        "env_key": "GOOGLE_API_KEY",
        "default_model": "gemini-2.5-flash",
        "route": {"kind": "litellm", "prefix": "gemini"},
        "list": {"url": "https://generativelanguage.googleapis.com/v1beta/models?key={k}",
                 "headers": lambda k: {}},
    },
    "openai": {
        "label": "OpenAI",
        "env_key": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
        "route": {"kind": "litellm", "prefix": "openai"},
        "list": {"url": "https://api.openai.com/v1/models",
                 "headers": lambda k: {"Authorization": f"Bearer {k}"}},
    },
    "grok": {  # xAI (console.x.ai) — ไม่มี native provider "xai" ใน litellm → openai-compatible
        "label": "Grok (xAI)",
        "env_key": "XAI_API_KEY",
        "default_model": "grok-4.1-fast",   # ตัวถูก+เร็ว เป็น default ปลอดภัย
        "route": {"kind": "openai_compat", "base_url": "https://api.x.ai/v1"},
        "list": {"url": "https://api.x.ai/v1/models",
                 "headers": lambda k: {"Authorization": f"Bearer {k}"}},
    },
    "deepseek": {  # platform.deepseek.com — native provider ของ litellm
        "label": "DeepSeek",
        "env_key": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-v4-flash",
        "route": {"kind": "litellm", "prefix": "deepseek"},
        "list": {"url": "https://api.deepseek.com/models",
                 "headers": lambda k: {"Authorization": f"Bearer {k}"}},
    },
    # M16-6 — aggregator ข้ามค่าย. crewai build นี้รู้จัก "openrouter" เป็น native provider →
    # ใช้ litellm prefix "openrouter/" ได้เลย (มันเก็บ vendor sub-path ของ model ครบ เช่น
    # "anthropic/claude-..." + เซ็ต base_url ให้อัตโนมัติ). /models คืน pricing+ctx+modality มาด้วย
    "openrouter": {
        "label": "OpenRouter",
        "env_key": "OPENROUTER_API_KEY",
        "default_model": "openai/gpt-4o-mini",
        "route": {"kind": "litellm", "prefix": "openrouter"},
        "list": {"url": "https://openrouter.ai/api/v1/models",
                 "headers": lambda k: {"Authorization": f"Bearer {k}"}},
    },
    # M16-6 — GitHub Models (OpenAI-compatible inference). ใช้ GitHub PAT ตัวเดียวกับ M9-3
    # (scope models:read) → ใครตั้ง GitHub integration ไว้แล้ว ได้ provider นี้อัตโนมัติ.
    # crewai ไม่มี native "github" + build นี้ไม่มี litellm fallback → route แบบ openai_compat
    "github": {
        "label": "GitHub Models",
        "env_key": "GITHUB_TOKEN",
        "default_model": "openai/gpt-4o",
        "route": {"kind": "openai_compat", "base_url": "https://models.github.ai/inference"},
        "list": {"url": "https://models.github.ai/catalog/models",
                 "headers": lambda k: {"Authorization": f"Bearer {k}",
                                       "Accept": "application/vnd.github+json",
                                       "X-GitHub-Api-Version": "2022-11-28"}},
    },
}

# derived views — คงชื่อเดิมไว้ให้โค้ดที่ import อยู่ (accounts/models/settings routes) ไม่พัง
# (single source of truth = PROVIDERS; ลำดับ provider คงเดิมตาม insertion order ของ dict)
ENV_KEY_MAP = {p: s["env_key"] for p, s in PROVIDERS.items()}
DEFAULT_CLOUD_MODELS = {p: s["default_model"] for p, s in PROVIDERS.items()}


# ─────────────────────────────────────────────────────────────────────────────
# M16-2 — Model normalize + classify
# ทุก provider คืนรูปร่าง model ต่างกัน → normalize เป็น ModelInfo รูปเดียว + จัดประเภท (kind)
# kind ใช้ใน UI: "chat" = ใช้เป็นสมอง agent ได้ (โชว์ default); อื่น ๆ ซ่อนหลัง "แสดงทั้งหมด"
#   ModelInfo = {id, label, kind, ctx, price_in, price_out}
#   kind ∈ chat | embed | image | audio | video | other
KIND_CHAT, KIND_EMBED, KIND_IMAGE, KIND_AUDIO, KIND_VIDEO, KIND_OTHER = \
    "chat", "embed", "image", "audio", "video", "other"


def _model_info(mid: str, label: str | None, kind: str,
                ctx=None, price_in=None, price_out=None) -> dict:
    return {"id": mid, "label": (label or mid), "kind": kind,
            "ctx": ctx, "price_in": price_in, "price_out": price_out}


def _kind_from_id(model_id: str) -> str:
    """เดา kind จากชื่อ id (ใช้กับ provider ที่ไม่บอก capability ตรง ๆ เช่น openai/grok/deepseek)

    หมายเหตุ: รุ่นที่ "รับภาพแต่ตอบเป็นข้อความ" (เช่น gpt-4o-vision) = chat — ห้าม map เป็น image.
    image = รุ่นที่ **ออก**ภาพ (dall-e/imagen/gpt-image); video = veo/sora; audio = whisper/tts/lyria.
    """
    s = model_id.lower()
    # specialized/tool models — ไม่ใช่ chat สมอง agent ทั่วไป (robotics/computer-use/research/AQA)
    if s == "aqa" or any(x in s for x in ("robotics", "computer-use", "antigravity",
                                          "deep-research", "moderation", "rerank", "guard")):
        return KIND_OTHER
    if any(x in s for x in ("embedding", "embed", "text-embedding")):
        return KIND_EMBED
    if any(x in s for x in ("whisper", "-tts", "tts-", "transcribe", "speech", "lyria")):
        return KIND_AUDIO
    if any(x in s for x in ("dall-e", "dalle", "gpt-image", "-image", "imagen",
                            "image-generation", "nano-banana", "stable-diffusion", "flux")):
        return KIND_IMAGE
    if any(x in s for x in ("veo", "sora", "-video", "video-")):
        return KIND_VIDEO
    return KIND_CHAT


def _parse_openai_like(data: dict) -> list[dict]:
    """OpenAI/Claude/Grok/DeepSeek: {data:[{id, display_name?, ...}]} — classify จาก id"""
    out = []
    for m in data.get("data") or []:
        if not isinstance(m, dict):
            continue
        mid = m.get("id") or m.get("name") or ""
        if not mid:
            continue
        label = m.get("display_name") or m.get("name") or mid
        out.append(_model_info(mid, label, _kind_from_id(mid)))
    return out


def _parse_gemini(data: dict) -> list[dict]:
    """Gemini: {models:[{name:'models/..', displayName, supportedGenerationMethods, inputTokenLimit}]}
    classify จาก supportedGenerationMethods (แม่นกว่าเดา id): generateContent=chat, embedContent=embed
    """
    out = []
    for m in data.get("models") or []:
        if not isinstance(m, dict):
            continue
        mid = (m.get("name") or "").split("/")[-1]
        if not mid:
            continue
        methods = m.get("supportedGenerationMethods") or []
        # ชื่อ id บอกชนิดชัดก่อน (image/audio/video/robotics) — Gemini รุ่นใหม่รองรับ generateContent
        # หมดแม้ output เป็นสื่ออื่น (เช่น Nano Banana=รูป, Lyria=เพลง, TTS=เสียง) จึงห้ามเชื่อ method อย่างเดียว
        idk = _kind_from_id(mid)
        if idk != KIND_CHAT:
            kind = idk
        elif any(x in methods for x in ("generateContent", "bidiGenerateContent")):
            kind = KIND_CHAT
        elif any(x in methods for x in ("embedContent", "embedText")):
            kind = KIND_EMBED
        else:
            kind = KIND_OTHER   # predict/answer ฯลฯ ที่ไม่ใช่ chat
        out.append(_model_info(mid, m.get("displayName"), kind, ctx=m.get("inputTokenLimit")))
    return out


def _per_mtok(v) -> float | None:
    """ราคา per-token (string/float) → USD per 1M token; None ถ้าแปลงไม่ได้ (M16-6)"""
    try:
        return round(float(v) * 1_000_000, 4)
    except (TypeError, ValueError):
        return None


def _parse_openrouter(data: dict) -> list[dict]:
    """OpenRouter: {data:[{id, name, pricing:{prompt,completion}, context_length, architecture:{output_modalities}}]}
    classify จาก output_modalities (แม่น); pricing เป็น USD/token → ×1e6 = ราคาต่อ 1M (M16-5 เอาไปใช้)
    """
    out = []
    for m in data.get("data") or []:
        if not isinstance(m, dict):
            continue
        mid = m.get("id") or ""
        if not mid:
            continue
        outmods = (m.get("architecture") or {}).get("output_modalities") or []
        if outmods:
            kind = (KIND_CHAT if "text" in outmods else KIND_IMAGE if "image" in outmods
                    else KIND_AUDIO if "audio" in outmods else KIND_VIDEO if "video" in outmods
                    else KIND_OTHER)
        else:
            kind = _kind_from_id(mid)
        pr = m.get("pricing") or {}
        out.append(_model_info(mid, m.get("name"), kind, ctx=m.get("context_length"),
                               price_in=_per_mtok(pr.get("prompt")), price_out=_per_mtok(pr.get("completion"))))
    return out


def _parse_github(data) -> list[dict]:
    """GitHub Models catalog — top-level อาจเป็น list หรือ {data:[..]}; field id/name + modalities (M16-6)"""
    items = data if isinstance(data, list) else (data.get("data") or data.get("models") or [])
    out = []
    for m in items:
        if not isinstance(m, dict):
            continue
        mid = m.get("id") or m.get("name") or ""
        if not mid:
            continue
        outmods = m.get("supported_output_modalities") or m.get("output_modalities") or []
        kind = (KIND_CHAT if "text" in outmods else _kind_from_id(mid)) if outmods else _kind_from_id(mid)
        out.append(_model_info(mid, m.get("friendly_name") or m.get("name"), kind))
    return out


# ผูก parser เข้า registry (วางหลังนิยามฟังก์ชัน เพื่อไม่ต้องเรียงนิยามไว้ก่อน PROVIDERS)
for _p in ("openai", "claude", "grok", "deepseek"):
    PROVIDERS[_p]["list"]["parse"] = _parse_openai_like
PROVIDERS["gemini"]["list"]["parse"] = _parse_gemini
PROVIDERS["openrouter"]["list"]["parse"] = _parse_openrouter
PROVIDERS["github"]["list"]["parse"] = _parse_github


def normalize_models(provider: str, data: dict) -> list[dict]:
    """raw จาก list-endpoint → list[ModelInfo] (M16-2)

    ใช้ parser เฉพาะของ provider (PROVIDERS[..]['list']['parse']); ถ้าไม่มี/พัง→ generic fallback
    (รองรับทั้ง {data:[..]} และ {models:[..]}, classify ด้วย _kind_from_id).
    """
    spec = PROVIDERS.get(provider) or {}
    fn = (spec.get("list") or {}).get("parse")
    if fn:
        try:
            return fn(data)
        except Exception:  # noqa: BLE001 — parser พัง (shape เปลี่ยน) → อย่าให้ทั้ง validate ล้ม
            pass
    items = data if isinstance(data, list) else (data.get("data") or data.get("models") or [])
    out = []
    for m in items:
        if not isinstance(m, dict):
            continue
        mid = m.get("id") or (m.get("name") or "").split("/")[-1]
        if mid:
            out.append(_model_info(mid, m.get("display_name") or m.get("displayName"), _kind_from_id(mid)))
    return out


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
    # verified กับ Google key จริง (มิ.ย.2026): 2.5-flash / 2.5-flash-lite = OK,
    # 2.5-pro = id ถูกแต่ free tier มัก 429 (rate limit). Gemini 3 (gemini-3-flash /
    # gemini-3.1-flash-lite) คืน 404 — ยังไม่เปิด/ชื่อ id ต่าง → ตัดออก ใส่กลับเมื่อยืนยัน id จริง
    "gemini": [
        {"model": "gemini-2.5-pro",         "label": "Gemini 2.5 Pro (อาจชน limit free tier)", "tier": "free", "in": 0, "out": 0},
        {"model": "gemini-2.5-flash",       "label": "Gemini 2.5 Flash",       "tier": "free", "in": 0, "out": 0},
        {"model": "gemini-2.5-flash-lite",  "label": "Gemini 2.5 Flash-Lite",  "tier": "free", "in": 0, "out": 0},
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
    # M14-3 — Grok (xAI). id อ้างชื่อจากภาพ CEO (มิ.ย.2026); ปรับให้ตรง API จริงได้ที่นี่ที่เดียว
    "grok": [
        {"model": "grok-4.3",        "label": "Grok 4.3 (flagship · 1M ctx)", "tier": "paid", "in": 5,   "out": 15},
        {"model": "grok-4.20",       "label": "Grok 4.20 (reasoning)",        "tier": "paid", "in": 3,   "out": 15},
        {"model": "grok-4.1-fast",   "label": "Grok 4.1 Fast",                "tier": "paid", "in": 0.5, "out": 2},
        {"model": "grok-build-0.1",  "label": "Grok Build 0.1 (coding)",      "tier": "paid", "in": 2,   "out": 10},
    ],
    # M14-3 — DeepSeek (ไม่มี subscription — API key ล้วน). ราคาถูกมากเป็นจุดขาย
    "deepseek": [
        {"model": "deepseek-v4-flash", "label": "DeepSeek V4-Flash",            "tier": "paid", "in": 0.3, "out": 1.1},
        {"model": "deepseek-v4-pro",   "label": "DeepSeek V4-Pro (1.6T MoE)",   "tier": "paid", "in": 0.6, "out": 2.2},
    ],
}


def cloud_models(provider: str) -> list[dict]:
    """รายชื่อ cloud model ของ provider (M11-13) — ว่าง = provider นั้นไม่มี catalog"""
    return CLOUD_CATALOG.get(provider, [])


def validate_cloud_key(provider: str, key: str, timeout: int = 12) -> dict:
    """ping provider ด้วย key → {ok, models?, error?} (M14-5, ใช้ registry M16-1)

    เรียก endpoint list-models (`PROVIDERS[provider]["list"]`) ที่ราคาถูก/ฟรี — 200 = key
    ใช้ได้ + ดึง id model จริงมาด้วย (M16-3 จะ persist เป็น cache ของ account).
    401/403 = key ผิด. ไม่ log/ไม่คาย key.
    """
    import urllib.error
    import urllib.request
    spec = PROVIDERS.get(provider)
    ep = spec.get("list") if spec else None
    if not ep:
        return {"ok": False, "error": f"provider {provider} ไม่รองรับ validate"}
    url = ep["url"].format(k=key)
    req = urllib.request.Request(url, headers=ep["headers"](key), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        # M16-2: คืน list[ModelInfo] (normalize+classify) แทน list[str] — M16-3 จะ persist เป็น cache
        return {"ok": True, "models": normalize_models(provider, data)}
    except urllib.error.HTTPError as e:
        msg = "key ไม่ถูกต้อง/หมดอายุ" if e.code in (401, 403) else f"HTTP {e.code}"
        return {"ok": False, "error": msg}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"เชื่อมต่อไม่ได้: {str(e)[:80]}"}


def cloud_price(provider: str, model: str) -> tuple[float, float] | None:
    """ราคา (in, out) USD/1M token ของ model (M11-13, ขยาย M16-5)

    ลำดับ: (1) account cache ที่มีราคาจริงต่อ key (เช่น OpenRouter ส่ง pricing มาด้วย)
    → (2) CLOUD_CATALOG (curated, hand-verified) → None (cost_guard เหมา per-provider ต่อ)
    """
    try:  # 1) ราคาจริงจาก list-endpoint ที่ cache ไว้บน account (model dynamic ที่ไม่อยู่ catalog)
        from ..services.account_store import account_store
        for acc in account_store.accounts_for(provider):
            for mi in acc.get("models") or []:
                if mi.get("id") == model and mi.get("price_in") is not None:
                    return (float(mi["price_in"]), float(mi.get("price_out") or 0.0))
    except Exception:  # noqa: BLE001 — pricing ห้ามทำ cost_guard ล้ม
        pass
    for m in CLOUD_CATALOG.get(provider, []):  # 2) catalog
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
    """provider ไหนมี API key พร้อมใช้ (M11-9/14) — มี key ใน .env default หรือใน key store"""
    from ..services.cloud_keys import cloud_keys
    return {prov: bool(os.environ.get(env) or cloud_keys.keys_for(prov))
            for prov, env in ENV_KEY_MAP.items()}


def _resolve_cloud_key(provider: str, account_id: str = "", key_id: str = "") -> str:
    """หา credential จริงของ cloud call — เรียงลำดับความสำคัญ (M14-4, ต่อยอด M11-14):

    1. `account_id` → ProviderAccount (api_key, เข้ารหัส DPAPI)
    2. `key_id` → cloud_keys store (M11-14 เดิม) — backward compat
    3. default: .env ก่อน แล้วค่อย key แรกใน store
    agent เก็บแค่ id อ้างอิง ไม่เก็บ secret.
    """
    if account_id:
        from ..services.account_store import account_store
        acc = account_store.get(account_id)
        if acc:
            tok = acc.get("secret", {}).get("key", "")
            if tok:
                return tok
    from ..services.cloud_keys import cloud_keys
    if key_id:
        k = cloud_keys.get(key_id)
        if k:
            return k
    env_key = os.environ.get(ENV_KEY_MAP.get(provider, ""), "")
    if env_key:
        return env_key
    store = cloud_keys.keys_for(provider)
    return store[0].get("key", "") if store else ""


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

    key = _resolve_cloud_key(cfg.provider, getattr(cfg, "account_id", "") or "",
                             getattr(cfg, "key_id", "") or "")
    if not key:
        raise MissingAPIKeyError(
            f"ยังไม่ได้ตั้ง API key สำหรับ {cfg.provider} — ใส่ได้ที่ Settings"
        )

    spec = PROVIDERS.get(cfg.provider)
    if spec is None:
        raise MissingAPIKeyError(f"ไม่รู้จัก provider {cfg.provider}")
    model = cfg.model or spec["default_model"]
    route = spec["route"]
    if route["kind"] == "openai_compat":
        # OpenAI-compatible endpoint (Grok/GitHub Models) — crewai จะ "ตัด prefix แรกของ model
        # เป็น provider" เสมอ ทำให้ชื่อ vendor ของ model หาย (เช่น "openai/gpt-4o"→"gpt-4o").
        # ใช้ passthrough "hosted_vllm/" (native ใน crewai) กันมันตัด → model คงครบ + ใช้ base_url เรา
        return LLM(model=f"hosted_vllm/{model}", api_key=key, base_url=route["base_url"], **extra)
    return LLM(model=f'{route["prefix"]}/{model}', api_key=key, **extra)


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
