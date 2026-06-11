"""M3-12 QA Gate — integration test daemon + Godot wallpaper

ตรวจ 5 ข้อ:
  1. agent เดินครบทุก zone (desk/cafe/meeting/dorm) ถึงจริงใน rect ที่ถูกต้อง
  2. ไม่ทะลุกำแพง — ทุกตำแหน่งที่สุ่มตรวจระหว่างเดิน ห้ามแตะ col 0 / row 0
  3. status sync daemon↔Godot — POST /task จริง: registry และ Godot เห็น
     working → idle ตรงกัน
  4. social ไม่ spam — proposal สดใหม่ + cooldown → หลายรอบ tick ต้องเงียบ
  5. social ยังมีชีวิต — cooldown 0 → ต้องเกิด meetup ภายใน timeout

ก่อนรัน: daemon (uvicorn daemon.main:app --port 8797) + Godot ต้องเปิดอยู่ทั้งคู่
ข้อควรระวัง: รันก่อน 22:00 — night shift (M3-5) จะจับ agent idle ไปนอนแทรกผลตรวจ
รัน: .venv\\Scripts\\python.exe tools\\qa_m3.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

from websockets.sync.client import connect

BASE = "http://localhost:8797"
QA_DUMP = Path(os.environ["APPDATA"]) / "Godot" / "app_userdata" / "ET Office Desktop" / "qa_positions.json"

# zone rect (x, y, w, h) — ตรงกับ office_builder.gd / agent_manager.gd
ZONE_RECTS = {
    "desk":    (6, 0, 7, 5),    # OPS FLOOR
    "cafe":    (6, 5, 7, 7),
    "meeting": (0, 5, 6, 7),
    "dorm":    (13, 5, 5, 7),
}
STATUS_ZONE = {
    "break": "cafe", "collab": "meeting", "sleep": "dorm",
    "working": "desk", "thinking": "desk", "idle": "desk",
}
GRID_W, GRID_H = 18, 12
WALK_TIMEOUT = 40.0

events: list[dict] = []
stop = threading.Event()
failures: list[str] = []


def ws_listener() -> None:
    with connect("ws://localhost:8797/ws") as ws:
        while not stop.is_set():
            try:
                msg = json.loads(ws.recv(timeout=2))
            except TimeoutError:
                continue
            if not msg.get("replay"):
                events.append(msg)


def http(method: str, path: str, payload: dict | None = None) -> dict | list:
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(f"{name}: {detail}")


def godot_dump() -> dict:
    """ขอ snapshot จาก Godot ผ่าน qa.dump event แล้วอ่านไฟล์ (รอจน ts ใหม่)"""
    before = time.time() - 1.0
    http("POST", "/event", {"type": "qa.dump", "data": {}})
    for _ in range(20):
        time.sleep(0.25)
        if QA_DUMP.exists():
            snap = json.loads(QA_DUMP.read_text(encoding="utf-8"))
            if snap.get("ts", 0) >= before:
                return snap
    raise RuntimeError("Godot ไม่ตอบ qa.dump — เปิด wallpaper อยู่ไหม?")


def in_rect(grid: list, rect: tuple) -> bool:
    x, y, w, h = rect
    return x <= grid[0] < x + w and y <= grid[1] < y + h


def on_wall(grid: list) -> bool:
    return grid[0] == 0 or grid[1] == 0 or not (
        0 <= grid[0] < GRID_W and 0 <= grid[1] < GRID_H)


def push_status_all(agent_ids: list[str], status: str) -> None:
    for aid in agent_ids:
        http("POST", "/event", {"type": "agent.status",
                                "data": {"agent_id": aid, "status": status}})


def wait_arrival(status: str) -> tuple[dict, list]:
    """รอทุกตัวหยุดเดิน — ระหว่างรอเก็บทุกตำแหน่งไว้ตรวจกำแพง"""
    sampled: list = []
    deadline = time.time() + WALK_TIMEOUT
    while time.time() < deadline:
        snap = godot_dump()
        sampled += [a["grid"] for a in snap["agents"]]
        if all(not a["walking"] for a in snap["agents"]):
            return snap, sampled
        time.sleep(1.5)
    return godot_dump(), sampled


def main() -> int:
    threading.Thread(target=ws_listener, daemon=True).start()
    time.sleep(1)

    agents = http("GET", "/agents")
    ids = [a["id"] for a in agents]
    print(f"agents: {[a['name'] for a in agents]}")
    saved_settings = http("GET", "/settings/social")
    http("PUT", "/settings/social", {"social_enabled": False})  # กัน social แทรกข้อ 1-3

    # Godot ต้อง spawn ครบก่อนเริ่ม (กัน gate ผ่านแบบกลวงเพราะ list ว่าง)
    for _ in range(15):
        try:
            if len(godot_dump().get("agents", [])) == len(ids):
                break
        except RuntimeError:
            pass  # Godot ยัง boot/ต่อ WS ไม่เสร็จ — รอแล้วลองใหม่
        time.sleep(3)
    else:
        print("FAIL: Godot spawn agents ไม่ครบ — เปิด wallpaper ก่อนรัน gate")
        return 1

    try:
        # --- 1+2: เดินครบทุก zone + ไม่ทะลุกำแพง -------------------------
        print("\n[1/5] เดินครบทุก zone (6 status)")
        all_samples: list = []
        for status in ("break", "collab", "sleep", "working", "thinking", "idle"):
            push_status_all(ids, status)
            snap, sampled = wait_arrival(status)
            all_samples += sampled
            zone = STATUS_ZONE[status]
            for a in snap["agents"]:
                check(f"{a['name']} {status}→{zone}",
                      in_rect(a["grid"], ZONE_RECTS[zone]) and a["status"] == status,
                      f"grid={a['grid']} status={a['status']}")

        print("\n[2/5] ไม่ทะลุกำแพง / ไม่หลุด grid")
        bad = [g for g in all_samples if on_wall(g)]
        check("ทุกตำแหน่งที่สุ่มตรวจอยู่ใน grid และไม่แตะ wall cell",
              not bad, f"เจอ {bad[:5]} จาก {len(all_samples)} samples" if bad else f"{len(all_samples)} samples สะอาด")

        # --- 3: status sync daemon↔Godot ผ่าน task จริง -------------------
        print("\n[3/5] status sync — POST /task จริง (รอ LLM)")
        events.clear()
        resp = http("POST", "/task", {"message": "สรุปสั้น ๆ 2 ประโยค: ทำไม pixel art ถึงเหมาะกับ desktop wallpaper"})
        task_agent = resp["agent"]
        deadline = time.time() + 240
        saw_working_registry = saw_working_godot = False
        while time.time() < deadline:
            reg = {a["name"]: a["status"] for a in http("GET", "/agents")}
            god = {a["name"]: a["status"] for a in godot_dump()["agents"]}
            if reg.get(task_agent) == "working":
                saw_working_registry = True
            if god.get(task_agent) == "working":
                saw_working_godot = True
            if any(e.get("type") in ("task.completed", "task.failed") for e in events):
                break
            time.sleep(3)
        done_type = next((e["type"] for e in events
                          if e.get("type") in ("task.completed", "task.failed")), "timeout")
        check("task จบ", done_type == "task.completed", done_type)
        check(f"registry เห็น {task_agent} working", saw_working_registry)
        check(f"Godot เห็น {task_agent} working", saw_working_godot)
        time.sleep(3)
        reg = {a["name"]: a["status"] for a in http("GET", "/agents")}
        god = {a["name"]: a["status"] for a in godot_dump()["agents"]}
        check("จบงานแล้วกลับ idle ตรงกันสองฝั่ง",
              reg.get(task_agent) == "idle" and god.get(task_agent) == "idle",
              f"registry={reg.get(task_agent)} godot={god.get(task_agent)}")

        # --- 4: social ไม่ spam ระหว่าง cooldown --------------------------
        print("\n[4/5] social ไม่ spam (cooldown 30 นาที + 4 ticks เร็ว)")
        http("POST", "/proposals", {"title": "[QA] cooldown marker", "detail": "",
                                    "proposed_by": ids[:1]})
        n_proposals = len(http("GET", "/proposals"))
        http("PUT", "/settings/social", {"social_enabled": True,
                                         "social_interval_sec": 8,
                                         "social_chance": 1.0,
                                         "proposal_cooldown_sec": 1800})
        events.clear()
        time.sleep(35)  # ≥4 ticks
        meetups = [e for e in events if e.get("type") == "social.meetup"]
        check("ไม่มี meetup ระหว่าง cooldown", not meetups, f"{len(meetups)} meetups")
        check("จำนวน proposal คงเดิม",
              len(http("GET", "/proposals")) == n_proposals)

        # --- 5: social ยังมีชีวิต (positive control) ----------------------
        print("\n[5/5] social ยังมีชีวิต — cooldown 0 ต้องเกิด meetup")
        http("PUT", "/settings/social", {"proposal_cooldown_sec": 0})
        events.clear()
        deadline = time.time() + 60
        meetup = None
        while time.time() < deadline and meetup is None:
            meetup = next((e for e in events if e.get("type") == "social.meetup"), None)
            time.sleep(2)
        check("เกิด social.meetup", meetup is not None)
        if meetup:  # รอแชทจบให้ agent กลับ idle ก่อนปิด gate
            for _ in range(60):
                if any(e.get("type") == "social.chat" for e in events):
                    break
                time.sleep(2)
    finally:
        stop.set()
        http("PUT", "/settings/social", {**{k: saved_settings[k] for k in (
            "social_interval_sec", "social_chance", "proposal_cooldown_sec")},
            "social_enabled": True})

    print("\n" + ("=" * 50))
    if failures:
        print(f"QA GATE M3: FAILED ({len(failures)})")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("QA GATE M3: PASSED ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
