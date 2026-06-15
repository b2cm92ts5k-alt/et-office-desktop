"""A-7 — ambient SFX (procedural placeholder) → godot/assets/sounds/*.wav

ตาม TASKS A-7: office hum, keyboard, server fan (optional/NICE) — สร้างด้วย numpy
เป็น loop ไร้รอยต่อ (crossfade หัว-ท้าย) drop-in swap ด้วยไฟล์เสียงจริงชื่อเดิมได้

  office_hum.wav   เสียงห้องเบา ๆ (brown noise + ฮัมต่ำ) — ambient bed
  keyboard.wav     เสียงพิมพ์คีย์บอร์ดสุ่ม ๆ
  server_fan.wav   พัดลม server หึ่ง ๆ คงที่

44100 Hz, mono, 16-bit PCM. ทุกไฟล์ normalize เบา (ambient ไม่ดัง)
รัน: ../.venv/Scripts/python.exe gen_ambient.py
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

OUT = Path(__file__).parent.parent / "godot" / "assets" / "sounds"
OUT.mkdir(parents=True, exist_ok=True)

SR = 44100
RNG = np.random.default_rng(7)


def _one_pole_lp(x: np.ndarray, a: float) -> np.ndarray:
    """low-pass หนึ่งขั้ว (a ยิ่งน้อยยิ่งกรองหนัก)"""
    y = np.empty_like(x)
    acc = 0.0
    for i in range(x.size):
        acc += a * (x[i] - acc)
        y[i] = acc
    return y


def _loop_crossfade(sig: np.ndarray, xfade: float = 0.25) -> np.ndarray:
    """ผสมหัว-ท้ายให้ loop ไร้รอยต่อ — sig ยาวเกินมา xfade วินาทีไว้ wrap"""
    x = int(xfade * SR)
    n = sig.size - x
    out = sig[:n].copy()
    t = np.linspace(0, 1, x, endpoint=False)
    out[:x] = sig[:x] * t + sig[n:n + x] * (1 - t)   # tail ไหลเข้า head
    return out


def _normalize(x: np.ndarray, peak: float) -> np.ndarray:
    m = np.max(np.abs(x)) or 1.0
    return x / m * peak


def _save(name: str, sig: np.ndarray) -> None:
    data = np.clip(sig, -1, 1)
    pcm = (data * 32767).astype("<i2")
    with wave.open(str(OUT / name), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print(f"saved {name}  ({sig.size / SR:.1f}s loop)")


def office_hum() -> np.ndarray:
    dur = 6.0
    n = int((dur + 0.3) * SR)
    white = RNG.standard_normal(n)
    brown = np.cumsum(white)                       # brown noise (รัมเบิลต่ำ)
    brown = _one_pole_lp(brown, 0.02)
    brown = _normalize(brown, 1.0)
    t = np.arange(n) / SR
    hum = 0.12 * np.sin(2 * np.pi * 100 * t) * (0.7 + 0.3 * np.sin(2 * np.pi * 0.13 * t))
    sig = _normalize(brown * 0.8 + hum, 0.22)
    return _loop_crossfade(sig)


def keyboard() -> np.ndarray:
    dur = 5.0
    n = int((dur + 0.25) * SR)
    sig = np.zeros(n)
    # คีย์สุ่ม ~7 ครั้ง/วินาที ช่วงพิมพ์รัว สลับเงียบ
    t_pos = 0.0
    while t_pos < dur:
        burst = bool(RNG.random() < 0.75)
        gap = RNG.uniform(0.04, 0.12) if burst else RNG.uniform(0.25, 0.7)
        t_pos += gap
        i = int(t_pos * SR)
        if i >= n:
            break
        klen = int(RNG.uniform(0.006, 0.014) * SR)   # เคาะสั้น ๆ
        env = np.exp(-np.linspace(0, 6, klen))       # attack ทันที decay เร็ว
        click = RNG.standard_normal(klen) * env
        click = _one_pole_lp(click, RNG.uniform(0.3, 0.6))  # โทนต่างกันต่อปุ่ม
        sig[i:i + klen] += click * RNG.uniform(0.5, 1.0)
    sig = _normalize(sig, 0.5)
    return _loop_crossfade(sig, 0.15)


def server_fan() -> np.ndarray:
    dur = 5.0
    n = int((dur + 0.3) * SR)
    white = RNG.standard_normal(n)
    air = _one_pole_lp(white, 0.25)                 # ลมพัด (กรองสูงออก)
    air = air - _one_pole_lp(air, 0.01)             # ตัดต่ำสุดทิ้ง (band-ish)
    air = _normalize(air, 1.0)
    t = np.arange(n) / SR
    rot = 0.10 * np.sin(2 * np.pi * 120 * t)        # โทนหมุนของพัดลม
    wobble = 0.85 + 0.15 * np.sin(2 * np.pi * 4.5 * t)
    sig = _normalize((air * 0.9 + rot) * wobble, 0.20)
    return _loop_crossfade(sig)


def main() -> None:
    _save("office_hum.wav", office_hum())
    _save("keyboard.wav", keyboard())
    _save("server_fan.wav", server_fan())


if __name__ == "__main__":
    main()
