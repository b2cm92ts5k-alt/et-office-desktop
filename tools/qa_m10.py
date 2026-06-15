"""QA Gate M10 — MCP client / Connect to the world (M10-1..M10-4)

รันแบบ import ตรง (ไม่ต้องมี daemon): python tools/qa_m10.py
ครอบคลุม: route wiring, MCP client handshake e2e (mock), service tools/call,
namespacing, task_router integration point
"""
from __future__ import annotations

import os
import sys
import tempfile
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root → import daemon

_results: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, info: str = "") -> None:
    _results.append((ok, name, info))
    print(("PASS" if ok else "FAIL"), "-", name, (f"  [{info}]" if info else ""))


MOCK = textwrap.dedent('''
import sys, json
def send(o): sys.stdout.write(json.dumps(o)+chr(10)); sys.stdout.flush()
for line in sys.stdin:
    line=line.strip()
    if not line: continue
    m=json.loads(line); mid=m.get("id"); meth=m.get("method")
    if meth=="initialize": send({"jsonrpc":"2.0","id":mid,"result":{"protocolVersion":"2024-11-05","capabilities":{},"serverInfo":{"name":"mock","version":"1"}}})
    elif meth=="notifications/initialized": pass
    elif meth=="tools/list": send({"jsonrpc":"2.0","id":mid,"result":{"tools":[{"name":"echo","description":"echo back","inputSchema":{"type":"object","properties":{"text":{"type":"string"}}}}]}})
    elif meth=="tools/call": send({"jsonrpc":"2.0","id":mid,"result":{"content":[{"type":"text","text":"echo: "+str(m["params"].get("arguments",{}).get("text",""))}]}})
    else: send({"jsonrpc":"2.0","id":mid,"error":{"code":-32601,"message":"nope"}})
''')


def main() -> None:
    import daemon.main
    from daemon.adapters.mcp_client import MCPStdioClient
    from daemon.services import task_router as TR
    from daemon.services.mcp_service import mcp_service
    from daemon.services.settings_store import settings_store

    print("--- M10-4 route wiring ---")
    paths = [getattr(r, "path", "") for r in daemon.main.app.routes]
    check("route GET/POST /mcp/servers", "/mcp/servers" in paths)
    check("route DELETE /mcp/servers/{name}", "/mcp/servers/{name}" in paths)

    f = os.path.join(tempfile.gettempdir(), "et_qa_mock_mcp.py")
    open(f, "w", encoding="utf-8").write(MOCK)
    try:
        print("\n--- M10-2 client handshake e2e ---")
        c = MCPStdioClient([sys.executable, f])
        c.start()
        check("initialize + alive", c.alive)
        tools = c.list_tools()
        check("tools/list → echo", any(t["name"] == "echo" for t in tools))
        check("tools/call echo", c.call_tool("echo", {"text": "hi"}) == "echo: hi")
        c.stop()

        print("\n--- M10-3 service + namespacing ---")
        settings_store._values["mcp_servers"] = [
            {"name": "mock", "command": f'"{sys.executable}" "{f}"', "enabled": True}]
        st = mcp_service.status()
        check("status ✓ tools", st and st[0]["status"].startswith("✓"), st[0]["status"] if st else "")
        names = [t["name"] for t in mcp_service.tools()]
        check("namespaced mcp__mock__echo", "mcp__mock__echo" in names, str(names))
        check("call ผ่าน service", mcp_service.call("mcp__mock__echo", {"text": "x"}) == "echo: x")
        check("unknown server → ข้อความชัด", "ไม่พบ" in mcp_service.call("mcp__nope__t", {}))
        mcp_service.stop_all()

        print("\n--- M10-3 task_router integration ---")
        check("task_router import mcp_service", hasattr(TR, "mcp_service"))
    finally:
        os.remove(f)
        settings_store._values["mcp_servers"] = []

    passed = sum(1 for ok, _, _ in _results if ok)
    total = len(_results)
    print(f"\n=== M10 QA: {passed}/{total} PASS ===")
    if passed != total:
        print("FAILED:", [n for ok, n, _ in _results if not ok])
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
