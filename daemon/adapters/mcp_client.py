"""MCP stdio client (M10-2) — JSON-RPC 2.0 over subprocess stdio

เชื่อม MCP server แบบ stdio (เช่น `npx -y @modelcontextprotocol/server-filesystem`)
→ list tools → call tool. sync (เรียกจาก tool loop thread ได้ตรง ๆ)

อ่าน stdout ผ่าน reader thread + queue กัน readline ค้างตลอดกาลถ้า server ไม่ตอบ
(timeout ได้จริง). stderr ทิ้ง (log ของ server เอง)
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading


class MCPError(Exception):
    pass


class MCPStdioClient:
    PROTOCOL = "2024-11-05"

    def __init__(self, command: list[str], env: dict | None = None) -> None:
        self.command = command
        self.env = {**os.environ, **(env or {})}
        self.proc: subprocess.Popen | None = None
        self._q: queue.Queue = queue.Queue()
        self._id = 0
        self._lock = threading.Lock()

    # --- lifecycle ---

    def start(self, timeout: float = 30) -> None:
        self.proc = subprocess.Popen(
            self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=self.env, text=True,
            encoding="utf-8", bufsize=1,
        )
        threading.Thread(target=self._reader, daemon=True).start()
        self._request("initialize", {
            "protocolVersion": self.PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "ET-Office", "version": "0.1"},
        }, timeout=timeout)
        self._notify("notifications/initialized")

    def stop(self) -> None:
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass
            self.proc = None

    @property
    def alive(self) -> bool:
        return bool(self.proc and self.proc.poll() is None)

    # --- MCP methods ---

    def list_tools(self) -> list[dict]:
        return (self._request("tools/list") or {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict | None = None, timeout: float = 60) -> str:
        res = self._request("tools/call", {"name": name, "arguments": arguments or {}}, timeout=timeout)
        parts = []
        for block in (res or {}).get("content", []):
            parts.append(block.get("text", "") if block.get("type") == "text"
                         else json.dumps(block, ensure_ascii=False))
        if (res or {}).get("isError"):
            return "MCP tool error: " + ("\n".join(parts) or "unknown")
        return "\n".join(parts) or json.dumps(res, ensure_ascii=False)

    # --- transport ---

    def _reader(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._q.put(json.loads(line))
            except json.JSONDecodeError:
                continue  # log line ที่ไม่ใช่ JSON-RPC — ข้าม

    def _send(self, obj: dict) -> None:
        if not self.proc or not self.proc.stdin:
            raise MCPError("MCP ยังไม่ได้เชื่อมต่อ")
        self.proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def _notify(self, method: str, params: dict | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def _request(self, method: str, params: dict | None = None, timeout: float = 30):
        with self._lock:
            self._id += 1
            rid = self._id
            self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
            import time
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MCPError(f"MCP timeout ({method})")
                try:
                    msg = self._q.get(timeout=remaining)
                except queue.Empty:
                    raise MCPError(f"MCP timeout ({method})")
                if msg.get("id") == rid:
                    if "error" in msg:
                        raise MCPError(str(msg["error"].get("message", "MCP error")))
                    return msg.get("result")
                # ข้อความอื่น (notification/log) — ข้าม
