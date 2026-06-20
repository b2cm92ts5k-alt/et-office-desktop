"""WebSocket hub — broadcast ทุก OEP event + event journal สำหรับ replay (M1-4)

Daemon เป็น source of truth: Godot/Sidebar ตายแล้วกลับมา ก็ replay journal
ต่อจากที่ค้างได้ — journal เก็บเป็น jsonl ที่ daemon/data/journal.jsonl
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import WebSocket

JOURNAL_PATH = Path(__file__).parent.parent / "data" / "journal.jsonl"
REPLAY_LIMIT = 100  # ส่ง event ล่าสุดกี่ตัวให้ client ที่เพิ่ง connect


class WSManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self.main_loop: asyncio.AbstractEventLoop | None = None  # set ตอน startup (M17) — ให้ thread emit ได้
        JOURNAL_PATH.parent.mkdir(exist_ok=True)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        # replay journal ล่าสุดให้ client ใหม่ (timeout กัน client ค้างระหว่าง replay)
        try:
            for event in self._read_journal_tail(REPLAY_LIMIT):
                await asyncio.wait_for(
                    ws.send_text(json.dumps({"replay": True, **event}, ensure_ascii=False)),
                    timeout=2.0,
                )
        except Exception:
            await self.disconnect(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, event: dict[str, Any]) -> None:
        event.setdefault("ts", datetime.now(timezone.utc).isoformat())
        self._append_journal(event)
        text = json.dumps(event, ensure_ascii=False)
        # snapshot ก่อนส่ง — ห้ามถือ lock ระหว่าง send และห้าม send แบบไม่มี timeout:
        # client ที่ถูก force-kill จะทำให้ send ค้างตลอดกาล → daemon ทั้งตัว deadlock
        async with self._lock:
            clients = list(self._clients)
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await asyncio.wait_for(ws.send_text(text), timeout=2.0)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)

    def broadcast_threadsafe(self, loop: asyncio.AbstractEventLoop, event: dict[str, Any]) -> None:
        """เรียกจาก worker thread (เช่น CrewAI kickoff) — ส่งเข้า event loop หลัก"""
        asyncio.run_coroutine_threadsafe(self.broadcast(event), loop)

    def emit(self, event: dict[str, Any]) -> None:
        """broadcast จาก thread ไหนก็ได้โดยใช้ main_loop ที่เก็บไว้ (M17 — tool-loop sync emit)
        ไม่มี loop (เช่น เทสนอกแอป) → เงียบ (ไม่ throw)"""
        if self.main_loop is not None:
            asyncio.run_coroutine_threadsafe(self.broadcast(event), self.main_loop)

    @property
    def client_count(self) -> int:
        return len(self._clients)

    # --- journal ---

    def _append_journal(self, event: dict[str, Any]) -> None:
        with JOURNAL_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _read_journal_tail(self, limit: int) -> list[dict[str, Any]]:
        if not JOURNAL_PATH.exists():
            return []
        lines = JOURNAL_PATH.read_text(encoding="utf-8").strip().splitlines()
        events = []
        for line in lines[-limit:]:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events


ws_manager = WSManager()
