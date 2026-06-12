"""PermissionGate (M6-8) — ทุก action ของ agent ต้องผ่านผู้ใช้ก่อนเสมอ (กฎจาก CEO)

Flow:
  tool loop (thread ของ task) → request() → broadcast permission.request →
  sidebar เด้ง dialog → POST /permissions/respond → ปลดล็อค thread → รัน/ไม่รัน tool

- "อนุมัติทั้ง task นี้" (approve_task) → action ที่เหลือของ task นั้นผ่านอัตโนมัติ
- ไม่ตอบภายใน TIMEOUT_SEC → deny (ปลอดภัยไว้ก่อน)
- ทุกคำขอ+คำตอบลง log_service เป็นหลักฐาน
"""
from __future__ import annotations

import asyncio
import threading
from uuid import uuid4

from .log_service import log_service
from .ws_manager import ws_manager

TIMEOUT_SEC = 300.0   # 5 นาที — ผู้ใช้ไม่อยู่หน้าจอ = ปฏิเสธ


class _Pending:
    def __init__(self, info: dict) -> None:
        self.info = info
        self.event = threading.Event()
        self.decision = "deny"        # default ถ้า timeout


class PermissionGate:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, _Pending] = {}
        self._task_approved: set[str] = set()   # task_id ที่กดอนุมัติยกชุดแล้ว
        self._loop: asyncio.AbstractEventLoop | None = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """เรียกจาก lifespan ตอน daemon บูต — ใช้ broadcast จาก worker thread"""
        self._loop = loop

    # --- ฝั่ง task thread (blocking) ---

    def request(self, task_id: str, agent_id: str, agent_name: str,
                tool: str, summary: str, detail: str = "") -> bool:
        """ขออนุญาต 1 action — block จนผู้ใช้ตอบ/timeout, คืน True = อนุญาต"""
        if task_id in self._task_approved:
            log_service.add("permission", f"auto-approve ({summary})", agent_id)
            self._broadcast({"type": "permission.auto",
                             "data": {"task_id": task_id, "agent_id": agent_id,
                                      "agent_name": agent_name, "summary": summary}})
            return True

        req_id = uuid4().hex[:12]
        info = {"request_id": req_id, "task_id": task_id, "agent_id": agent_id,
                "agent_name": agent_name, "tool": tool,
                "summary": summary, "detail": detail[:2000]}
        pending = _Pending(info)
        with self._lock:
            self._pending[req_id] = pending

        log_service.add("permission", f"ขออนุญาต: {summary}", agent_id)
        self._broadcast({"type": "permission.request", "data": info})

        pending.event.wait(TIMEOUT_SEC)
        with self._lock:
            self._pending.pop(req_id, None)

        decision = pending.decision
        if decision == "approve_task":
            self._task_approved.add(task_id)
        approved = decision in ("approve", "approve_task")
        log_service.add("permission",
                        f"{'อนุญาต' if approved else 'ปฏิเสธ'} ({decision}): {summary}",
                        agent_id)
        self._broadcast({"type": "permission.resolved",
                         "data": {"request_id": req_id, "decision": decision,
                                  "approved": approved}})
        return approved

    def finish_task(self, task_id: str) -> None:
        """task จบ — ล้างสิทธิ์อนุมัติยกชุด"""
        self._task_approved.discard(task_id)

    # --- ฝั่ง API (event loop) ---

    def respond(self, request_id: str, decision: str) -> bool:
        """decision: approve | deny | approve_task — คืน False ถ้าคำขอหมดอายุไปแล้ว"""
        with self._lock:
            pending = self._pending.get(request_id)
            if pending is None:
                return False
            pending.decision = decision
            pending.event.set()
            return True

    def pending(self) -> list[dict]:
        with self._lock:
            return [p.info for p in self._pending.values()]

    def _broadcast(self, event: dict) -> None:
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(ws_manager.broadcast(event), self._loop)


permission_gate = PermissionGate()
