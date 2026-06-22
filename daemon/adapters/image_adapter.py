"""ImageAdapter (M17-1) — สร้างภาพต่อ provider (คนละ API กับ chat)

ภาพ ≠ chat: แต่ละเจ้า endpoint/รูปแบบต่างกัน จึงต้องมี backend แยก (ไม่ผ่าน CrewAI LLM).
รับ provider/model/key/prompt → คืน list[bytes] (PNG/JPEG) ให้ tool generate_image (M17-2)
เซฟลง workspace. credential ฝั่ง tool เป็นคน resolve (reuse `_resolve_cloud_key` ของ M16)
แล้วส่ง key ดิบเข้ามาที่นี่ — adapter ไม่ยุ่งกับ store/secret เอง (ไม่ log key).

v1 (CEO เคาะ 2026-06-21): Gemini (ฟรี — Nano Banana/Imagen) + OpenAI (paid); OpenRouter = v2.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

_TIMEOUT = 120          # สร้างภาพช้ากว่า chat — เผื่อเวลา
_MAX_N = 4              # กันยิงเยอะเกิน (CEO เคาะ: default 1, สูงสุด 4)
_ASPECT_SIZE = {"1:1": "1024x1024", "16:9": "1792x1024", "9:16": "1024x1792"}


class ImageError(Exception):
    """ข้อผิดพลาดสร้างภาพ — tool เอาไปคืนเป็น observation ให้ agent อ่าน (ไม่ throw ดิบ)"""


def _post_json(url: str, headers: dict, body: dict, timeout: int = _TIMEOUT) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _b64(s: str) -> bytes:
    return base64.b64decode(s)


# ── backends ────────────────────────────────────────────────────────────────
def _gemini_nano(model: str, key: str, prompt: str, n: int, aspect: str) -> list[bytes]:
    """Nano Banana (gemini-*-image) — generateContent คืน inline image (1 รูป/call → loop ตาม n)"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    out: list[bytes] = []
    for _ in range(n):
        data = _post_json(url, {}, body)
        got = False
        for cand in data.get("candidates", []) or []:
            for part in cand.get("content", {}).get("parts", []) or []:
                inline = part.get("inline_data") or part.get("inlineData")
                if inline and inline.get("data"):
                    out.append(_b64(inline["data"]))
                    got = True
        if not got:  # โดน safety block หรือไม่มีรูป
            fb = data.get("promptFeedback", {}).get("blockReason")
            raise ImageError(f"Gemini ไม่คืนรูป{f' (block: {fb})' if fb else ''}")
    return out


def _gemini_imagen(model: str, key: str, prompt: str, n: int, aspect: str) -> list[bytes]:
    """Imagen (imagen-*) — :predict คืนหลายรูปต่อ call (sampleCount)"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:predict?key={key}"
    body = {"instances": [{"prompt": prompt}],
            "parameters": {"sampleCount": n, "aspectRatio": aspect}}
    data = _post_json(url, {}, body)
    out = [_b64(p["bytesBase64Encoded"]) for p in data.get("predictions", []) or []
           if p.get("bytesBase64Encoded")]
    if not out:
        raise ImageError("Imagen ไม่คืนรูป (อาจติด policy หรือบัญชีต้องเปิด billing)")
    return out


def _gemini(model: str, key: str, prompt: str, n: int, aspect: str) -> list[bytes]:
    return (_gemini_imagen if "imagen" in model.lower() else _gemini_nano)(model, key, prompt, n, aspect)


def _openai(model: str, key: str, prompt: str, n: int, aspect: str) -> list[bytes]:
    """gpt-image-1 / dall-e-3 — POST /v1/images/generations (b64_json)"""
    size = _ASPECT_SIZE.get(aspect, "1024x1024")
    body: dict = {"model": model, "prompt": prompt, "n": n, "size": size}
    if model.startswith("dall-e"):
        body["response_format"] = "b64_json"   # gpt-image-1 คืน b64 อยู่แล้ว
        body["n"] = 1 if model == "dall-e-3" else n   # dall-e-3 รองรับ n=1
    data = _post_json("https://api.openai.com/v1/images/generations",
                      {"Authorization": f"Bearer {key}"}, body)
    out = [_b64(d["b64_json"]) for d in data.get("data", []) or [] if d.get("b64_json")]
    if not out:
        raise ImageError("OpenAI ไม่คืนรูป")
    return out


def _openrouter(model: str, key: str, prompt: str, n: int, aspect: str) -> list[bytes]:
    """OpenRouter image-output models (M24-4) — /chat/completions + modalities:[image,text]

    image model ของ OpenRouter (เช่น google/gemini-2.5-flash-image-preview) คืนรูปใน
    choices[].message.images[].image_url.url เป็น data URL base64 — 1 รูป/call → loop ตาม n
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "X-Title": "ET Office"}
    body = {"model": model, "messages": [{"role": "user", "content": prompt}],
            "modalities": ["image", "text"]}
    out: list[bytes] = []
    for _ in range(n):
        data = _post_json(url, headers, body)
        got = False
        for ch in data.get("choices", []) or []:
            for img in (ch.get("message", {}) or {}).get("images", []) or []:
                u = (img.get("image_url") or {}).get("url") or ""
                if u.startswith("data:") and "," in u:
                    out.append(_b64(u.split(",", 1)[1]))
                    got = True
        if not got:
            raise ImageError("OpenRouter ไม่คืนรูป (model นี้อาจไม่ใช่ image-output หรือ key ไม่มีสิทธิ์)")
    return out


_BACKENDS = {"gemini": _gemini, "openai": _openai, "openrouter": _openrouter}

# provider ที่สร้างภาพได้ (UI/picker ใช้กรอง)
IMAGE_PROVIDERS = {"gemini", "openai", "openrouter"}

# default model ต่อ provider เมื่อ agent ไม่ได้เลือก (gemini = ฟรี Nano Banana ตามมติ CEO)
DEFAULT_IMAGE_MODEL = {"gemini": "gemini-2.5-flash-image", "openai": "gpt-image-1",
                       "openrouter": "google/gemini-2.5-flash-image-preview"}


def supported(provider: str) -> bool:
    return provider in IMAGE_PROVIDERS


def generate(provider: str, model: str, key: str, prompt: str,
             *, n: int = 1, aspect: str = "1:1") -> list[bytes]:
    """สร้างภาพ → list[bytes]. ข้อผิดพลาดทุกชนิด normalize เป็น ImageError (message สั้น, ไม่คาย key)"""
    fn = _BACKENDS.get(provider)
    if fn is None:
        raise ImageError(f"{provider} สร้างภาพไม่ได้")
    if not key:
        raise ImageError(f"ยังไม่มี key ของ {provider} ที่สร้างภาพได้")
    p = (prompt or "").strip()
    if not p:
        raise ImageError("ต้องมี prompt")
    n = max(1, min(int(n or 1), _MAX_N))
    aspect = aspect if aspect in _ASPECT_SIZE else "1:1"
    try:
        imgs = fn(model, key, p, n, aspect)
    except ImageError:
        raise
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:200]
        raise ImageError(f"HTTP {e.code}: {detail}")
    except Exception as e:  # noqa: BLE001
        raise ImageError(f"สร้างภาพล้มเหลว: {str(e)[:160]}")
    if not imgs:
        raise ImageError("ไม่ได้รูปกลับมา")
    return imgs
