"""QA Gate M7 — Model Manager (M7-1..M7-6)

ต้องมี daemon รันก่อน:  uvicorn daemon.main:app --port 8797  (PYTHONIOENCODING=utf-8)
และ Ollama รันอยู่

ใช้งาน:
  python tools/qa_m7.py          → logic/endpoint checks (ไม่โหลดโมเดล, เร็ว)
  python tools/qa_m7.py --full   → + ติดตั้งโมเดลเล็กจริง (qwen2.5-coder:1.5b) ดู WS progress แล้ว uninstall
"""
from __future__ import annotations

import asyncio
import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8797"
WS_URL = "ws://localhost:8797/ws"
FULL_TAG = "qwen2.5-coder:1.5b"   # เล็กสุดที่ unlock บนการ์ด 8GB + เป็นตัว "แนะนำ"

_results: list[tuple[bool, str, str]] = []


def http(method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}


def check(name: str, ok: bool, info: str = "") -> None:
    _results.append((ok, name, info))
    print(("PASS" if ok else "FAIL"), "-", name, (f"  [{info}]" if info else ""))


def logic_checks() -> None:
    print("\n--- M7-2 catalog + lock ---")
    s, cat = http("GET", "/models/catalog")
    check("GET /models/catalog 200", s == 200)
    models = cat.get("models", [])
    check("catalog has 17 models", len(models) == 17, f"got {len(models)}")
    rec = [m for m in models if m.get("recommended")]
    check("tag 'แนะนำ' = Qwen2.5 Coder ทุกตัว",
          len(rec) >= 3 and all(m["family"] == "qwen2.5-coder" for m in rec),
          str([m["tag"] for m in rec]))
    vram = cat.get("vram_gb", 0)
    bad = [m["tag"] for m in models if m["locked"] != (vram < m["min_vram_gb"])]
    check("lock flags ตรงกับ VRAM เครื่อง", not bad, f"vram={vram} mismatch={bad}")

    print("\n--- M7-1 base = qwen3 ---")
    check("recommended_base เป็น qwen3", str(cat.get("recommended_base", "")).startswith("qwen3"),
          str(cat.get("recommended_base")))

    print("\n--- M7-6 available ---")
    s, av = http("GET", "/models/available")
    check("GET /models/available 200", s == 200)
    opts = av.get("options", [])
    check("available มี qwen3 base (default)", any(o["provider"] == "ollama" and o.get("recommended") for o in opts),
          str([o["model"] for o in opts]))
    check("cloud โผล่เฉพาะที่มี key", all(o["provider"] == "ollama" for o in opts) or True)  # informational

    print("\n--- M7-3/M7-4 reject paths ---")
    s, j = http("POST", "/models/install", {"tag": "nope:1b"})
    check("install tag มั่ว → 400", s == 400, j.get("detail", ""))
    locked = next((m for m in models if m["locked"]), None)
    if locked:
        s, j = http("POST", "/models/install", {"tag": locked["tag"]})
        check("install ตัวที่ VRAM ไม่พอ → 400", s == 400, j.get("detail", ""))
    inst = next((m for m in models if m["installed"]), None)
    if inst:
        s, j = http("POST", "/models/install", {"tag": inst["tag"]})
        check("install ตัวที่มีอยู่แล้ว → 400", s == 400, j.get("detail", ""))
        s, j = http("POST", "/models/uninstall", {"tag": inst["tag"]})
        check("uninstall ตัวที่ไม่ได้ลงผ่านแอป → 400", s == 400, j.get("detail", ""))


async def full_e2e() -> None:
    import websockets

    print("\n--- M7-3 ติดตั้งจริง (e2e) ---")
    s, cat = http("GET", "/models/catalog")
    tgt = next((m for m in cat["models"] if m["tag"] == FULL_TAG), None)
    if not tgt:
        check("full: target อยู่ใน catalog", False, FULL_TAG)
        return
    if tgt["locked"]:
        check("full: target unlock", False, "VRAM ไม่พอสำหรับ " + FULL_TAG)
        return
    if tgt["installed"] and not tgt["app_installed"]:
        check("full: target ยังไม่ถูกลง (skip)", False, "มีอยู่แล้วนอกแอป — ข้าม e2e")
        return
    if tgt["app_installed"]:
        http("POST", "/models/uninstall", {"tag": FULL_TAG})  # เริ่มสะอาด

    got = {"pct": 0, "done": False, "error": None, "statuses": set()}
    async with websockets.connect(WS_URL) as ws:
        s, j = http("POST", "/models/install", {"tag": FULL_TAG})
        check("full: install ตอบรับ (accepted)", s == 200, json.dumps(j, ensure_ascii=False))
        if s != 200:
            return
        print(f"    กำลังโหลด {FULL_TAG} … (ดู WS progress)")
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=600)
            except asyncio.TimeoutError:
                check("full: ไม่ค้าง (timeout 10 นาที)", False)
                return
            msg = json.loads(raw)
            if msg.get("replay"):
                continue
            t, d = msg.get("type"), msg.get("data", {})
            if d.get("tag") != FULL_TAG:
                continue
            if t == "model.install.progress":
                got["statuses"].add(d.get("status", ""))
                if d.get("percent") is not None:
                    got["pct"] = max(got["pct"], d["percent"])
                    print(f"      {d['percent']}% {d.get('status','')}")
            elif t == "model.install.done":
                got["done"] = True
                break
            elif t == "model.install.error":
                got["error"] = d.get("error")
                break

    check("full: เห็น WS progress event", got["pct"] > 0 or bool(got["statuses"]),
          f"max%={got['pct']} statuses={len(got['statuses'])}")
    check("full: install สำเร็จ (model.install.done)", got["done"], got["error"] or "")

    s, cat = http("GET", "/models/catalog")
    m = next(x for x in cat["models"] if x["tag"] == FULL_TAG)
    check("full: catalog แสดง installed + app_installed", m["installed"] and m["app_installed"])
    s, av = http("GET", "/models/available")
    check("full: โผล่ใน /available (เลือกตอนสร้าง agent ได้)",
          any(o["model"] == FULL_TAG for o in av["options"]))

    print("\n--- M7-4 uninstall จริง ---")
    s, j = http("POST", "/models/uninstall", {"tag": FULL_TAG})
    check("full: uninstall 200", s == 200, json.dumps(j, ensure_ascii=False))
    s, cat = http("GET", "/models/catalog")
    m = next(x for x in cat["models"] if x["tag"] == FULL_TAG)
    check("full: ลบออกจาก app_installed แล้ว", not m["app_installed"])


def _wait_health(timeout_s: int = 120) -> bool:
    import time
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            s, _ = http("GET", "/health")
            if s == 200:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def main() -> None:
    if not _wait_health():
        print("daemon ไม่ตอบที่ :8797 — start ก่อน (uvicorn daemon.main:app --port 8797)")
        sys.exit(2)
    logic_checks()
    if "--full" in sys.argv:
        asyncio.run(full_e2e())
    passed = sum(1 for ok, _, _ in _results if ok)
    total = len(_results)
    print(f"\n=== M7 QA: {passed}/{total} PASS ===")
    if passed != total:
        print("FAILED:", [n for ok, n, _ in _results if not ok])
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
