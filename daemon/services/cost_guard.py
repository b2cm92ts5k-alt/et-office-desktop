"""CostGuard (M11-10, §5.3) — กันค่า cloud API บานปลาย

ป้องกันกรณี model เล็กหลุดทำ loop เรียก cloud ไม่จบจน bill พุ่ง: เกิน budget ต่อวัน/ชั่วโมง
→ task ถัดไปที่เป็น cloud จะ fallback กลับ local + แจ้งใน activity feed.

ข้อจำกัด: CrewAI ไม่คาย token usage ของ cloud → ประเมิน token จากความยาว message (~4 ตัว/token).
เป็น "guard กันบานปลาย" ไม่ใช่ billing แม่นยำ — ตั้ง budget เผื่อ buffer.
"""
from __future__ import annotations

import threading
import time

from .settings_store import settings_store

# USD ต่อ 1M token (รวม in+out คร่าว ๆ — ปรับได้ตามราคาจริง ณ มิ.ย.2026)
PRICE_PER_MTOK: dict[str, float] = {
    "claude": 6.0,
    "openai": 5.0,
    "gemini": 0.3,
    "grok": 8.0,      # M14 — เหมา in+out คร่าว (ตัว flagship); per-model จาก catalog แม่นกว่า
    "deepseek": 1.0,  # M14 — DeepSeek ถูกมาก
    "ollama": 0.0,   # local ฟรี
}
_WINDOW_KEEP = 86400  # เก็บ event ย้อนหลัง 24 ชม. พอสำหรับ cap รายวัน

# M17 — ราคาประมาณต่อ "รูป" (USD) สำหรับ generate_image (ภาพคิดต่อรูป ไม่ใช่ต่อ token)
# gemini Nano Banana = free tier (โควต้า) → 0; per-model override มาก่อน per-provider
IMAGE_PRICE_PER_IMG: dict[str, float] = {"gemini": 0.0, "openai": 0.04}
IMAGE_PRICE_MODEL: dict[str, float] = {
    "gpt-image-1": 0.04, "dall-e-3": 0.04,
    "imagen-4.0-generate-001": 0.04, "imagen-4.0-ultra-generate-001": 0.06,
    "imagen-4.0-fast-generate-001": 0.02,
}


def est_tokens(messages: list[dict]) -> int:
    """ประเมิน token จากความยาว content (~4 ตัวอักษร/token) — ใช้กับ cloud ที่ไม่คาย usage"""
    chars = sum(len(str(m.get("content", ""))) for m in messages)
    return chars // 4


class CostGuard:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[tuple[float, float]] = []  # (ts, usd)

    def record(self, provider: str, model: str, tokens_in: int, tokens_out: int) -> float:
        """บันทึกค่าใช้จ่าย 1 ครั้ง → คืน usd (local = 0)

        ใช้ราคา per-model จาก CLOUD_CATALOG ก่อน (M11-13) — แม่นกว่าเหมา per-provider;
        ถ้า model ไม่อยู่ใน catalog ค่อย fallback เป็น flat PRICE_PER_MTOK[provider].
        """
        from ..adapters.llm_adapter import cloud_price
        per = cloud_price(provider, model)
        if per is not None:
            usd = tokens_in / 1_000_000 * per[0] + tokens_out / 1_000_000 * per[1]
        else:
            usd = (tokens_in + tokens_out) / 1_000_000 * PRICE_PER_MTOK.get(provider, 0.0)
        if usd > 0:
            with self._lock:
                now = time.time()
                self._events.append((now, usd))
                self._events = [(t, u) for t, u in self._events if now - t <= _WINDOW_KEEP]
        return usd

    def image_price(self, provider: str, model: str) -> float:
        """ราคาประมาณต่อรูป (USD) — per-model ก่อน แล้ว per-provider; 0 = ฟรี (M17)"""
        return IMAGE_PRICE_MODEL.get(model, IMAGE_PRICE_PER_IMG.get(provider, 0.0))

    def record_image(self, provider: str, model: str, n: int = 1) -> float:
        """บันทึกค่าใช้จ่ายการสร้างภาพ n รูป → คืน usd (free = 0) (M17-5)"""
        usd = self.image_price(provider, model) * max(1, int(n or 1))
        if usd > 0:
            with self._lock:
                now = time.time()
                self._events.append((now, usd))
                self._events = [(t, u) for t, u in self._events if now - t <= _WINDOW_KEEP]
        return usd

    def spent(self, window_sec: float) -> float:
        now = time.time()
        with self._lock:
            return round(sum(u for t, u in self._events if now - t <= window_sec), 4)

    def over_budget(self) -> bool:
        """เกิน cap รายวันหรือรายชั่วโมงไหม (cap = 0 หรือปิด guard → ไม่จำกัด)"""
        if not settings_store.get("cost_guard_enabled"):
            return False
        daily = float(settings_store.get("cost_daily_usd") or 0)
        hourly = float(settings_store.get("cost_hourly_usd") or 0)
        if daily > 0 and self.spent(_WINDOW_KEEP) >= daily:
            return True
        if hourly > 0 and self.spent(3600) >= hourly:
            return True
        return False

    def status(self) -> dict:
        return {
            "enabled": bool(settings_store.get("cost_guard_enabled")),
            "spent_today": self.spent(_WINDOW_KEEP),
            "spent_hour": self.spent(3600),
            "cap_daily": float(settings_store.get("cost_daily_usd") or 0),
            "cap_hourly": float(settings_store.get("cost_hourly_usd") or 0),
            "over_budget": self.over_budget(),
        }


cost_guard = CostGuard()
