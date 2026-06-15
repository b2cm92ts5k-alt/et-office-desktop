"""MCPService (M10-3) — จัดการ MCP server ที่ตั้งไว้ + เปิดเผย tools ให้ agent

server เก็บใน settings 'mcp_servers' = [{"name","command","enabled"}]
tools ตั้งชื่อ namespaced: mcp__<server>__<tool> (กันชนกับ tool ในตัว + รู้ว่ามาจาก server ไหน)
client เปิดแบบ lazy + cache (เปิด subprocess ครั้งแรกที่ใช้ แล้วใช้ซ้ำ)
"""
from __future__ import annotations

import shlex
import threading

from ..adapters.mcp_client import MCPError, MCPStdioClient
from .settings_store import settings_store

PREFIX = "mcp__"


class MCPService:
    def __init__(self) -> None:
        self._clients: dict[str, MCPStdioClient] = {}
        self._lock = threading.Lock()

    def configured(self) -> list[dict]:
        return list(settings_store.get("mcp_servers") or [])

    def _client(self, srv: dict) -> MCPStdioClient:
        name = srv["name"]
        with self._lock:
            c = self._clients.get(name)
            if c and c.alive:
                return c
            # posix=False กัน backslash ใน Windows path โดนกิน แล้วถอด quote ที่ค้างออกเอง
            parts = [p.strip('"').strip("'") for p in shlex.split(srv["command"], posix=False)]
            c = MCPStdioClient(parts)
            c.start()
            self._clients[name] = c
            return c

    def tools(self) -> list[dict]:
        """[{name: mcp__srv__tool, args, desc}] — ข้าม server ที่ปิด/error เงียบ ๆ"""
        out: list[dict] = []
        for srv in self.configured():
            if not srv.get("enabled", True):
                continue
            try:
                for t in self._client(srv).list_tools():
                    props = (t.get("inputSchema") or {}).get("properties") or {}
                    out.append({
                        "name": f"{PREFIX}{srv['name']}__{t['name']}",
                        "args": list(props.keys()),
                        "desc": t.get("description", ""),
                    })
            except Exception:
                continue
        return out

    def call(self, namespaced: str, args: dict) -> str:
        srv_name, _, tool = namespaced[len(PREFIX):].partition("__")
        for srv in self.configured():
            if srv["name"] == srv_name:
                try:
                    return self._client(srv).call_tool(tool, args)
                except MCPError as e:
                    return f"MCP error: {e}"
                except Exception as e:  # noqa: BLE001
                    return f"MCP tool ล้มเหลว: {e}"
        return f"ไม่พบ MCP server: {srv_name}"

    def status(self) -> list[dict]:
        """สำหรับ UI — server + จำนวน tools หรือ error"""
        rows = []
        for srv in self.configured():
            row = {"name": srv["name"], "command": srv["command"],
                   "enabled": srv.get("enabled", True)}
            if not row["enabled"]:
                row["status"] = "ปิดอยู่"
            else:
                try:
                    row["status"] = f"✓ {len(self._client(srv).list_tools())} tools"
                except Exception as e:  # noqa: BLE001
                    row["status"] = f"✗ {str(e)[:60]}"
            rows.append(row)
        return rows

    def disconnect(self, name: str) -> None:
        c = self._clients.pop(name, None)
        if c:
            c.stop()

    def stop_all(self) -> None:
        for c in self._clients.values():
            c.stop()
        self._clients.clear()


mcp_service = MCPService()
