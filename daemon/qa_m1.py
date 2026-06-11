"""M1-15 QA gate — full-loop test: WS connect → POST /task (Thai) → รอ events ครบ
รัน: .venv\\Scripts\\python.exe daemon\\qa_m1.py
"""
import json
import sys
import threading
import time
import urllib.request

from websockets.sync.client import connect

BASE = "http://localhost:8797"
events: list[dict] = []
done = threading.Event()


def ws_listener() -> None:
    with connect("ws://localhost:8797/ws") as ws:
        while not done.is_set():
            try:
                msg = json.loads(ws.recv(timeout=5))
            except TimeoutError:
                continue
            if msg.get("replay"):
                continue
            events.append(msg)
            print(f"  [WS] {msg.get('type')}", flush=True)
            if msg.get("type") in ("task.completed", "task.failed"):
                done.set()


def post_json(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def main() -> int:
    t = threading.Thread(target=ws_listener, daemon=True)
    t.start()
    time.sleep(1)

    msg = "ช่วยวางแผนงานสัปดาห์นี้ให้หน่อย สรุปสั้น ๆ 3 ข้อพอ"
    print(f"POST /task: {msg}")
    resp = post_json("/task", {"message": msg})
    print(f"  routed to: {resp['agent']} (task {resp['task_id']})")

    if not done.wait(timeout=300):
        print("FAIL: timeout waiting for task.completed")
        return 1

    types = [e.get("type") for e in events]
    print(f"\nevent sequence: {types}")

    expected = ["task.routing", "agent.status", "task.completed", "agent.status"]
    ok = all(t in types for t in set(expected)) and "task.failed" not in types
    if not ok:
        print("FAIL: event sequence incomplete or task failed")
        for e in events:
            print(json.dumps(e, ensure_ascii=False)[:300])
        return 1

    output = next(e for e in events if e["type"] == "task.completed")["data"]["output"]
    print(f"\n--- agent output ---\n{output[:500]}")
    print("\n--- M1 QA GATE PASSED ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
