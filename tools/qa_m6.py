"""M6-10 QA Gate — Agent Workforce ครบวงจร

ตรวจ 5 หมวดตาม task board:
  1. fire/hire + role ครบวงจร — POST /roles/save → จ้าง agent จาก role →
     agent.created broadcast → DELETE /agents → agent.deleted broadcast
  2. agent สร้าง-แก้ไฟล์จริงใน workspace — POST /task → qwen tool loop →
     permission.request เด้งก่อนไฟล์เกิด → approve → ไฟล์อยู่จริง
  3. ทุก action ผ่าน permission gate — deny แล้วไฟล์ต้องไม่เกิด,
     approve_task แล้ว action ถัดไปต้องเป็น permission.auto (ไม่เด้งถามซ้ำ),
     ทุกคำขอ+คำตอบลง log SQLite
  4. action นอก workspace ถูก block — ../ traversal + absolute path →
     WorkspaceError (ทดสอบตรงที่ tool_executor หลังตั้ง workspace)
  5. terminal window จำตำแหน่ง+ขนาดข้าม restart — ย้ายหน้าต่างจริง →
     collapse (บังคับ save) → ปิด process → เปิดใหม่ → rect เดิม

ก่อนรัน: daemon + Ollama ต้องเปิดอยู่ (gate เปิด/ปิด sidebar เองในข้อ 5)
รัน: .venv\\Scripts\\python.exe tools\\qa_m6.py
     --skip-llm   ข้ามข้อ 2-3 (ไม่มี Ollama/รีบ) — ผลถือว่า partial
     --skip-gui   ข้ามข้อ 5 (เครื่องไม่มีจอ)
"""
from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from ctypes import wintypes
from pathlib import Path

from websockets.sync.client import connect

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # console cp1252 พิมพ์ไทยไม่ได้

BASE = "http://localhost:8797"
HOST_PY = REPO / "sidebar" / "host.py"
UI_STATE = REPO / "sidebar" / "data" / "ui_state.json"
TERMINAL_TITLE = "ET Terminal"
TASK_TIMEOUT = 420          # qwen3:8b ทีละ step — เผื่อใจ 7 นาทีต่อ task

QA_ROLE_MD = """---
name: ET QA Hire
role: QA Hire Test
avatar: "🧪"
color: "#00ff9f"
keywords: [qa-m6-hire-test]
---
คุณคือ agent ทดสอบจาก qa_m6 — ตอบสั้นที่สุดเสมอ"""

user32 = ctypes.windll.user32
events: list[dict] = []
ev_lock = threading.Lock()
stop = threading.Event()
failures: list[str] = []


# --------------------------------------------------------------- infra
def ws_listener() -> None:
    while not stop.is_set():
        try:
            with connect(BASE.replace("http", "ws") + "/ws") as ws:
                while not stop.is_set():
                    try:
                        msg = json.loads(ws.recv(timeout=2))
                    except TimeoutError:
                        continue
                    if not msg.get("replay"):
                        with ev_lock:
                            events.append(msg)
        except Exception:
            time.sleep(1)


def http(method: str, path: str, payload: dict | None = None) -> dict | list:
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""),
          flush=True)
    if not ok:
        failures.append(f"{name}: {detail}")


def wait_event(etype: str, pred=None, timeout: float = 30.0, start: int = 0) -> dict | None:
    """รอ event ชนิด etype ตั้งแต่ index start — คืน event หรือ None ถ้า timeout"""
    deadline = time.time() + timeout
    i = start
    while time.time() < deadline:
        with ev_lock:
            batch = events[i:]
        for off, ev in enumerate(batch):
            if ev.get("type") == etype and (pred is None or pred(ev.get("data", {}))):
                return ev
        i += len(batch)
        time.sleep(0.3)
    return None


def run_task_with_responder(message: str, decide) -> tuple[dict | None, list[dict]]:
    """POST /task แล้วตอบ permission.request ของ task นี้ด้วย decide(data) → decision
    คืน (task.completed/failed event, รายการ permission events ของ task นี้)"""
    with ev_lock:
        n0 = len(events)
    resp = http("POST", "/task", {"message": message})
    task_id = resp["task_id"]
    perm_events: list[dict] = []
    deadline = time.time() + TASK_TIMEOUT
    seen = n0
    while time.time() < deadline:
        with ev_lock:
            batch = list(events[seen:])
        seen += len(batch)
        for ev in batch:
            data = ev.get("data", {})
            if data.get("task_id") != task_id:
                continue
            if ev["type"] in ("permission.request", "permission.auto"):
                perm_events.append(ev)
                if ev["type"] == "permission.request":
                    http("POST", "/permissions/respond",
                         {"request_id": data["request_id"], "decision": decide(data)})
            elif ev["type"] in ("task.completed", "task.failed"):
                return ev, perm_events
        time.sleep(0.3)
    return None, perm_events


# --------------------------------------------------------------- sections
def section_hire_fire() -> None:
    print("\n[1/5] fire/hire + role ครบวงจร", flush=True)
    n_roles = len(http("GET", "/roles"))
    preset = http("POST", "/roles/save", {"filename": "qa-m6-hire", "text": QA_ROLE_MD})
    check("POST /roles/save parse frontmatter ถูก",
          preset.get("name") == "ET QA Hire" and "qa-m6-hire-test" in preset.get("keywords", []),
          json.dumps(preset, ensure_ascii=False)[:160])
    roles = http("GET", "/roles")
    check("role ใหม่โผล่ใน GET /roles", len(roles) == n_roles + 1,
          f"{n_roles} → {len(roles)}")

    with ev_lock:
        n0 = len(events)
    agent = http("POST", "/agents", {
        "name": preset["name"], "role": preset["role"], "avatar": preset["avatar"],
        "color": preset["color"], "keywords": preset["keywords"],
        "system_prompt": preset["system_prompt"]})
    aid = agent["id"]
    created = wait_event("agent.created", lambda d: d.get("id") == aid, 10, n0)
    check("จ้างแล้ว broadcast agent.created", created is not None)
    check("system_prompt จาก role ผูกเข้า agent",
          "qa_m6" in agent.get("system_prompt", ""), agent.get("system_prompt", "")[:80])
    check("agent อยู่ใน GET /agents",
          any(a["id"] == aid for a in http("GET", "/agents")))

    with ev_lock:
        n1 = len(events)
    http("DELETE", f"/agents/{aid}")
    deleted = wait_event("agent.deleted", lambda d: d.get("agent_id") == aid, 10, n1)
    check("ไล่ออกแล้ว broadcast agent.deleted (Godot despawn ฟัง event นี้)",
          deleted is not None)
    check("agent หายจาก registry",
          not any(a["id"] == aid for a in http("GET", "/agents")))
    try:
        http("DELETE", f"/agents/{aid}")
        check("ไล่ออกซ้ำต้อง 404", False, "ได้ 200")
    except urllib.error.HTTPError as e:
        check("ไล่ออกซ้ำต้อง 404", e.code == 404, f"code={e.code}")

    # เก็บกวาด role ทดสอบ (อยู่นอก git อยู่แล้ว แต่ไม่ทิ้งขยะไว้)
    (REPO / "daemon" / "data" / "roles" / "qa-m6-hire.md").unlink(missing_ok=True)


def section_workspace_approve(ws_dir: Path) -> None:
    print("\n[2/5] agent สร้างไฟล์จริงใน workspace (approve ทุก action)", flush=True)
    try:
        http("PUT", "/settings/workspace", {"path": str(ws_dir) + "\\no-such-dir"})
        check("ตั้ง workspace path มั่ว ต้อง 400", False, "ได้ 200")
    except urllib.error.HTTPError as e:
        check("ตั้ง workspace path มั่ว ต้อง 400", e.code == 400, f"code={e.code}")
    http("PUT", "/settings/workspace", {"path": str(ws_dir)})
    got = http("GET", "/settings/workspace")
    check("GET /settings/workspace ตรงที่ตั้ง", got.get("valid") and got.get("path") == str(ws_dir),
          json.dumps(got, ensure_ascii=False))

    target = ws_dir / "qa_m6.txt"
    file_seen_at_request = []

    def decide(data: dict) -> str:
        file_seen_at_request.append(target.exists())
        return "approve"

    done, perms = run_task_with_responder(
        'สร้างไฟล์ qa_m6.txt เนื้อหา "hello from qa m6" ด้วย write_file', decide)
    check("task จบ (completed)", done is not None and done["type"] == "task.completed",
          done["type"] if done else "timeout")
    check("มี permission.request อย่างน้อย 1 ครั้ง",
          any(e["type"] == "permission.request" for e in perms), f"{len(perms)} events")
    check("ตอน permission เด้ง ไฟล์ยังไม่เกิด (gate มาก่อน action จริง)",
          bool(file_seen_at_request) and not any(file_seen_at_request),
          str(file_seen_at_request))
    check("ไฟล์เกิดจริงใน workspace", target.is_file())
    if target.is_file():
        check("เนื้อหาตรงที่สั่ง", "hello from qa m6" in target.read_text(encoding="utf-8"),
              target.read_text(encoding="utf-8")[:80])


def section_permission_gate(ws_dir: Path) -> None:
    print("\n[3/5] permission gate: deny + อนุมัติยกชุด + log", flush=True)

    # --- deny: ปฏิเสธทุกคำขอ → ไฟล์ต้องไม่เกิด
    denied = ws_dir / "denied.txt"
    done, perms = run_task_with_responder(
        'สร้างไฟล์ denied.txt เนื้อหา "should not exist"', lambda d: "deny")
    check("deny แล้ว task ยังจบไม่ค้าง", done is not None, "" if done else "timeout")
    check("deny แล้วไฟล์ต้องไม่เกิด", not denied.exists())
    check("มีคำขอถูกปฏิเสธจริง (ไม่ใช่ model ไม่ลองทำ)",
          any(e["type"] == "permission.request" for e in perms), f"{len(perms)} events")

    # --- approve_task: คำขอแรกอนุมัติยกชุด → action ถัดไปต้องเป็น permission.auto
    decisions = iter(["approve_task"])
    done, perms = run_task_with_responder(
        'สร้างไฟล์ 2 ไฟล์ทีละไฟล์ด้วย write_file สองครั้ง: b1.txt เนื้อหา "one" '
        'แล้วตามด้วย b2.txt เนื้อหา "two"',
        lambda d: next(decisions, "approve"))
    check("approve_task แล้ว task จบ", done is not None and done["type"] == "task.completed",
          done["type"] if done else "timeout")
    n_req = sum(1 for e in perms if e["type"] == "permission.request")
    n_auto = sum(1 for e in perms if e["type"] == "permission.auto")
    check("เด้งถามแค่ครั้งแรกครั้งเดียว", n_req == 1, f"request={n_req}")
    check("action ถัดไป auto-approve (permission.auto)", n_auto >= 1, f"auto={n_auto}")
    check("ไฟล์เกิดครบทั้ง 2", (ws_dir / "b1.txt").is_file() and (ws_dir / "b2.txt").is_file(),
          f"b1={(ws_dir / 'b1.txt').is_file()} b2={(ws_dir / 'b2.txt').is_file()}")

    # --- ทุกคำขอ+คำตอบลง SQLite
    logs = [l for l in http("GET", "/logs") if l.get("type") == "permission"]
    check("permission log ลง SQLite (ขอ/อนุญาต/ปฏิเสธ/auto)",
          any("ขออนุญาต" in l["message"] for l in logs)
          and any("ปฏิเสธ" in l["message"] for l in logs)
          and any("auto-approve" in l["message"] for l in logs),
          f"{len(logs)} permission logs")


def section_sandbox(ws_dir: Path) -> None:
    print("\n[4/5] action นอก workspace ถูก block", flush=True)
    # import หลังตั้ง workspace ผ่าน API แล้ว — settings_store อ่านไฟล์เดียวกันตอน import
    from daemon.services.tool_executor import WorkspaceError, execute

    (ws_dir.parent / "qa_m6_outside.txt").write_text("secret", encoding="utf-8")
    attempts = [
        ("read_file ../",      "read_file",  {"path": "../qa_m6_outside.txt"}),
        ("write_file ..\\",    "write_file", {"path": "..\\evil.txt", "content": "x"}),
        ("move ออกนอก root",   "move",       {"src": "qa_m6.txt", "dst": "../stolen.txt"}),
        ("delete นอก root",    "delete",     {"path": "../qa_m6_outside.txt"}),
        ("absolute path",      "read_file",  {"path": "C:\\Windows\\win.ini"}),
        ("ซ้อนหลายชั้น",        "list_dir",   {"path": "a/../../.."}),
    ]
    for label, tool, args in attempts:
        try:
            out = execute(tool, args)
            check(f"block {label}", False, f"ผ่านได้: {out[:80]}")
        except WorkspaceError:
            check(f"block {label}", True)
    check("ไฟล์นอก workspace ยังอยู่ครบ",
          (ws_dir.parent / "qa_m6_outside.txt").exists() and not (ws_dir.parent / "evil.txt").exists())
    (ws_dir.parent / "qa_m6_outside.txt").unlink(missing_ok=True)

    # path ถูกกติกาใต้ workspace ต้องยังทำงานปกติ (กัน sandbox ตึงเกิน)
    ok = execute("write_file", {"path": "sub/inner.txt", "content": "ok"})
    check("path ใต้ workspace ยังใช้ได้", (ws_dir / "sub" / "inner.txt").is_file(), ok[:80])


# --------------------------------------------------------------- GUI (ข้อ 5)
def window_rect(title: str) -> tuple[int, int, int, int] | None:
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return None
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def wait_terminal(timeout: float = 25.0) -> tuple[int, int, int, int]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        rect = window_rect(TERMINAL_TITLE)
        if rect and rect[2] > 0:
            return rect
        time.sleep(0.5)
    raise RuntimeError("ไม่พบหน้าต่าง ET Terminal")


def section_terminal_state() -> None:
    print("\n[5/5] terminal window จำตำแหน่ง+ขนาดข้าม restart", flush=True)
    proc = subprocess.Popen([sys.executable, str(HOST_PY)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_terminal()
        time.sleep(3)  # รอหน้าเพจโหลด + _snap

        # ย้าย+ปรับขนาดหน้าต่างจริงด้วย Win32 (เหมือน user ลาก)
        tx, ty, tw, th = 160, 140, 520, 320
        hwnd = user32.FindWindowW(None, TERMINAL_TITLE)
        user32.SetWindowPos(hwnd, 0, tx, ty, tw, th, 0x0004)  # SWP_NOZORDER
        time.sleep(2)

        # collapse → terminal ซ่อน + บังคับ save geometry (set_visible(False) เรียก save)
        http("POST", "/event", {"type": "sidebar.toggle", "data": {"expanded": False}})
        time.sleep(2.5)
        check("collapse แล้ว terminal ซ่อนตาม sidebar (M6-5)",
              not user32.IsWindowVisible(hwnd))
        saved = json.loads(UI_STATE.read_text(encoding="utf-8")).get("terminal", {})
        geo_ok = all(abs(saved.get(k, -99) - v) <= 2 for k, v in
                     zip(("x", "y", "w", "h"), (tx, ty, tw, th)))
        check("geometry ลง ui_state.json", geo_ok, json.dumps(saved))

        # expand → โผล่กลับที่เดิม
        http("POST", "/event", {"type": "sidebar.toggle", "data": {"expanded": True}})
        time.sleep(2.5)
        check("expand แล้ว terminal โผล่กลับ", bool(user32.IsWindowVisible(hwnd)))
        before = window_rect(TERMINAL_TITLE)
        check("ตำแหน่งหลัง expand คงเดิม",
              before is not None and all(abs(a - b) <= 2 for a, b in zip(before, (tx, ty, tw, th))),
              str(before))
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    time.sleep(2)

    # restart → ต้องกลับมาที่เดิมจาก ui_state.json
    proc = subprocess.Popen([sys.executable, str(HOST_PY)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        rect = wait_terminal()
        time.sleep(2)
        rect = window_rect(TERMINAL_TITLE)
        check("เปิดใหม่แล้วกลับตำแหน่ง+ขนาดเดิม (ข้าม restart)",
              all(abs(a - b) <= 2 for a, b in zip(rect, (160, 140, 520, 320))),
              f"rect={rect}")
    finally:
        proc.terminate()
        proc.wait(timeout=10)


# --------------------------------------------------------------- main
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-llm", action="store_true")
    parser.add_argument("--skip-gui", action="store_true")
    args = parser.parse_args()

    threading.Thread(target=ws_listener, daemon=True).start()
    time.sleep(1)
    health = http("GET", "/health")
    print(f"daemon: {health}", flush=True)
    prev_ws = str(http("GET", "/settings/workspace").get("path", ""))

    ws_dir = Path(tempfile.mkdtemp(prefix="qa_m6_ws_"))
    print(f"workspace ทดสอบ: {ws_dir}", flush=True)
    try:
        section_hire_fire()
        if args.skip_llm:
            print("\n[2-3/5] SKIPPED (--skip-llm)", flush=True)
            http("PUT", "/settings/workspace", {"path": str(ws_dir)})
        else:
            if not health.get("ollama_ok"):
                print("FAIL: Ollama ไม่พร้อม — ข้อ 2-3 ต้องใช้ LLM จริง", flush=True)
                failures.append("ollama down")
                return 1
            section_workspace_approve(ws_dir)
            section_permission_gate(ws_dir)
        section_sandbox(ws_dir)
        if args.skip_gui:
            print("\n[5/5] SKIPPED (--skip-gui)", flush=True)
        else:
            section_terminal_state()
    finally:
        stop.set()
        try:  # คืน workspace เดิมของ user
            http("PUT", "/settings/workspace", {"path": prev_ws})
        except Exception:
            pass

    print("\n" + "=" * 50, flush=True)
    if failures:
        print(f"QA GATE M6: FAILED ({len(failures)})", flush=True)
        for f in failures:
            print(f"  - {f}", flush=True)
        return 1
    print("QA GATE M6: PASSED ✅", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
