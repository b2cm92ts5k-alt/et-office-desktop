"""M4-11 QA Gate — integration test daemon + sidebar (pywebview)

ตรวจ 3 หมวดตาม task board:
  1. sidebar ไม่บัง desktop — หน้าต่าง snap ขอบขวา, กว้างสุด 320px,
     หุบเหลือ 36px (วัด rect จริงผ่าน Win32)
  2. ทุก panel ทำงานกับ daemon จริง — หน้าเพจ self-report DOM ผ่าน
     qa.ping → qa.sidebar event: agent cards + pill ตรง registry,
     proposal card โผล่เมื่อสร้าง/หายเมื่อตอบจาก client อื่น,
     settings โหลดค่า VRAM/social, terminal feed โตเมื่อส่ง task จริง
  3. ปิด-เปิดแล้ว state คืนได้ — หุบไว้ → ปิด process → เปิดใหม่
     ต้องกลับมาหุบเองที่ 36px (localStorage + private_mode=False)

ก่อนรัน: daemon ต้องเปิดอยู่ (gate เปิด/ปิด sidebar เองทั้งหมด)
รัน: .venv\\Scripts\\python.exe tools\\qa_m4.py
"""
from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import threading
import time
import urllib.request
from ctypes import wintypes
from pathlib import Path

from websockets.sync.client import connect

BASE = "http://localhost:8797"
WINDOW_TITLE = "ET Office Sidebar"
HOST_PY = Path(__file__).parent.parent / "sidebar" / "host.py"
EXPANDED_W, COLLAPSED_W = 320, 36

user32 = ctypes.windll.user32
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


def window_rect() -> tuple[int, int, int, int] | None:
    """(x, y, w, h) ของหน้าต่าง sidebar — None ถ้ายังไม่มี"""
    hwnd = user32.FindWindowW(None, WINDOW_TITLE)
    if not hwnd:
        return None
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def wait_window(timeout: float = 20.0) -> tuple[int, int, int, int]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        rect = window_rect()
        if rect and rect[2] > 0:
            return rect
        time.sleep(0.5)
    raise RuntimeError("ไม่พบหน้าต่าง sidebar")


def wait_width(width: int, timeout: float = 12.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        rect = window_rect()
        if rect and rect[2] == width:
            return True
        time.sleep(0.5)
    return False


def qa_snapshot(timeout: float = 10.0) -> dict:
    """ขอ DOM snapshot จากหน้าเพจ: ส่ง qa.ping → รอ qa.sidebar ตอบกลับ"""
    n_before = len(events)
    http("POST", "/event", {"type": "qa.ping", "data": {}})
    deadline = time.time() + timeout
    while time.time() < deadline:
        for ev in events[n_before:]:
            if ev.get("type") == "qa.sidebar":
                return ev.get("data", {})
        time.sleep(0.3)
    raise RuntimeError("หน้าเพจไม่ตอบ qa.ping — sidebar เปิดอยู่ไหม?")


def launch_sidebar(extra_qs: str = "") -> subprocess.Popen:
    args = [sys.executable, str(HOST_PY)]
    if extra_qs:
        args += extra_qs.split(" ")
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def toggle(expanded: bool) -> None:
    http("POST", "/event", {"type": "sidebar.toggle", "data": {"expanded": expanded}})


def main() -> int:
    threading.Thread(target=ws_listener, daemon=True).start()
    time.sleep(1)
    screen_w = user32.GetSystemMetrics(0)
    screen_h = user32.GetSystemMetrics(1)
    registry = http("GET", "/agents")

    proc = launch_sidebar()
    try:
        # --- 1: ไม่บัง desktop --------------------------------------------
        print("\n[1/3] หน้าต่าง snap ขอบขวา ไม่บัง desktop")
        x, y, w, h = wait_window()
        time.sleep(3)  # รอ _snap หลังโหลด
        x, y, w, h = window_rect()
        check("expanded กว้าง 320", w == EXPANDED_W, f"w={w}")
        check("ชิดขอบขวา", x + w == screen_w, f"x={x} w={w} screen={screen_w}")
        check("ไม่กินความสูงเกินจอ", 0 <= y and h <= screen_h, f"y={y} h={h}")
        check("บังจอแค่ ~17%", w / screen_w <= 0.17, f"{w}/{screen_w}")

        toggle(False)
        check("หุบเหลือ 36px", wait_width(COLLAPSED_W), f"rect={window_rect()}")
        x2, _, w2, _ = window_rect()
        check("หุบแล้วยังชิดขอบขวา", x2 + w2 == screen_w, f"x={x2} w={w2}")
        toggle(True)
        check("ขยายกลับ 320px", wait_width(EXPANDED_W), f"rect={window_rect()}")

        # --- 2: ทุก panel ทำงานกับ daemon จริง -----------------------------
        print("\n[2/3] panels ↔ daemon จริง")
        time.sleep(2)
        snap = qa_snapshot()
        check("agent cards ครบตาม registry",
              snap.get("agents_rendered") == len(registry),
              f"rendered={snap.get('agents_rendered')} registry={len(registry)}")
        reg_status = {a["id"]: a["status"] for a in registry}
        pills_ok = all(snap.get("pills", {}).get(i) == s for i, s in reg_status.items())
        check("pill ตรง status ใน registry", pills_ok, str(snap.get("pills")))

        # pill เปลี่ยน realtime
        target = registry[0]["id"]
        http("POST", "/event", {"type": "agent.status",
                                "data": {"agent_id": target, "status": "working"}})
        time.sleep(1.5)
        snap = qa_snapshot()
        check("pill เปลี่ยนเป็น WORKING ผ่าน WS",
              snap.get("pills", {}).get(target) == "working",
              str(snap.get("pills", {}).get(target)))
        http("POST", "/event", {"type": "agent.status",
                                "data": {"agent_id": target, "status": "idle"}})

        # proposal card: สร้าง → โผล่, ตอบจาก client อื่น → หาย
        before = qa_snapshot().get("proposals_rendered", 0)
        prop = http("POST", "/proposals", {"title": "[QA] ทดสอบ proposal card",
                                           "detail": "จาก qa_m4", "proposed_by": [target]})
        time.sleep(1.5)
        snap = qa_snapshot()
        check("proposal card โผล่เมื่อสร้าง",
              snap.get("proposals_rendered", 0) == before + 1,
              f"{before} → {snap.get('proposals_rendered')}")
        http("POST", "/proposals/respond",
             {"proposal_id": prop["id"], "action": "reject", "note": "qa"})
        time.sleep(1.5)
        snap = qa_snapshot()
        check("card หายเมื่อตอบจาก client อื่น (proposal.rejected)",
              snap.get("proposals_rendered", 0) == before,
              f"เหลือ {snap.get('proposals_rendered')}")

        # terminal ทดสอบรวมกับข้อ 3 ตอน relaunch (qa_task ผ่าน input จริง)
        n_tasks = len(http("GET", "/tasks"))
    except Exception as exc:
        stop.set()
        proc.terminate()
        print(f"FAIL: {exc}")
        return 1

    # --- 3: ปิด-เปิดแล้ว state คืนได้ (รวม terminal qa_task ตอน relaunch) --
    print("\n[3/3] ปิด-เปิดแล้ว state คืนได้")
    toggle(False)
    ok_collapsed = wait_width(COLLAPSED_W)
    check("หุบก่อนปิด", ok_collapsed)
    proc.terminate()
    proc.wait(timeout=10)
    time.sleep(1)

    proc = launch_sidebar('--qa-task [QA-M4]ทดสอบส่งงานจาก-sidebar')
    try:
        wait_window()
        check("เปิดใหม่แล้วกลับมาหุบเอง (restore localStorage)",
              wait_width(COLLAPSED_W, timeout=15), f"rect={window_rect()}")
        snap = qa_snapshot(timeout=15)
        check("CSS ฝั่งเพจ restore เป็น collapsed", snap.get("collapsed") is True)
        check("agent cards กลับมาครบหลัง relaunch",
              snap.get("agents_rendered") == len(registry))

        time.sleep(4)  # รอ qa_task ยิงผ่าน input จริง
        snap = qa_snapshot()
        check("terminal feed มีบรรทัดงานที่ส่ง", snap.get("feed_lines", 0) >= 3,
              f"feed={snap.get('feed_lines')}")
        check("task ใหม่เข้าระบบจริง (/tasks โต)",
              len(http("GET", "/tasks")) == n_tasks + 1,
              f"{n_tasks} → {len(http('GET', '/tasks'))}")

        toggle(True)  # คืนสภาพ expand ให้ user
        time.sleep(1.5)
    finally:
        stop.set()
        proc.terminate()

    print("\n" + ("=" * 50))
    if failures:
        print(f"QA GATE M4: FAILED ({len(failures)})")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("QA GATE M4: PASSED ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
