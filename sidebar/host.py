"""Sidebar host (M4-1/M4-3) — pywebview + WebView2 หน้าต่าง frameless ชิดขอบจอขวา

หน้าที่ฝั่ง Python มีแค่ window management — data ทั้งหมด JS คุยกับ daemon ตรง ๆ
หน้าเพจ serve โดย daemon (http://localhost:8797/sidebar/) ให้เป็น same-origin

สำคัญ: ไม่ใช้ js_api bridge ของ pywebview — การ inject bridge ทำ JS ทั้งหน้าพัง
บนเครื่อง dev (WebView2 COM mismatch) ปุ่มหุบ/ขยายจึงส่งสัญญาณผ่าน daemon แทน:
JS → POST /event {type:"sidebar.toggle"} → host ฟัง WS อยู่ → resize หน้าต่าง
(รายละเอียดใน docs/ADR-M4-1-sidebar-host.md)

รัน:  .venv\\Scripts\\python.exe sidebar\\host.py
QA:   --qa-task "ข้อความ"  ให้หน้าเพจส่ง task ผ่าน input จริงหลังโหลด (query param)
      --qa-toggle          ให้หน้าเพจสลับ collapse → expand อัตโนมัติ (ทดสอบ M4-3)
"""
from __future__ import annotations

import argparse
import json
import threading
import urllib.parse
import urllib.request

import pystray
import webview
from PIL import Image, ImageDraw
from websockets.sync.client import connect as ws_connect

DAEMON_URL = "http://localhost:8797/sidebar/index.html"
DAEMON_WS = "ws://localhost:8797/ws"
DAEMON_HTTP = "http://localhost:8797"
EXPANDED_W = 320
COLLAPSED_W = 36
TASKBAR_H = 48        # กันที่ taskbar ล่าง


class SidebarWindow:
    def __init__(self) -> None:
        self.window: webview.Window | None = None
        self.expanded = True

    def set_expanded(self, expanded: bool) -> None:
        self.expanded = bool(expanded)
        self._snap()

    def _snap(self) -> None:
        """resize + ชิดขอบขวาเสมอ"""
        screen = webview.screens[0]
        w = EXPANDED_W if self.expanded else COLLAPSED_W
        h = screen.height - TASKBAR_H
        self.window.resize(w, h)
        self.window.move(screen.width - w, 0)

    def listen_toggle(self, tray: "Tray | None" = None) -> None:
        """WS client เล็ก ๆ — sidebar.toggle → resize, agent.status → tray badge,
        task.completed / proposal.created → notification toast (M4-9)"""
        working: set[str] = set()
        while True:
            try:
                with ws_connect(DAEMON_WS) as ws:
                    while True:
                        msg = json.loads(ws.recv())
                        if msg.get("replay"):
                            continue
                        mtype = msg.get("type")
                        data = msg.get("data", {})
                        if mtype == "sidebar.toggle":
                            self.set_expanded(bool(data.get("expanded", True)))
                        elif tray is None:
                            continue
                        elif mtype == "agent.status":
                            if data.get("status") in ("working", "thinking"):
                                working.add(data.get("agent_id", ""))
                            else:
                                working.discard(data.get("agent_id", ""))
                            tray.set_badge(len(working))
                        elif mtype == "task.completed":
                            tray.notify("✓ Task เสร็จแล้ว",
                                        _trim(data.get("output", ""), 120))
                        elif mtype == "proposal.created":
                            tray.notify("💡 ข้อเสนอใหม่จากทีม",
                                        _trim(data.get("title", ""), 120))
            except Exception:
                import time
                time.sleep(3)  # daemon หาย → รอแล้วต่อใหม่


def _trim(s: str, n: int) -> str:
    s = " ".join(str(s or "").split())
    return s[:n] + "…" if len(s) > n else s


class Tray:
    """System tray (M4-8) — pystray + ไอคอน ET วาดด้วย Pillow
    icon จริง (A-8) มาแทนได้: วางไฟล์ assets/tray.png ข้าง host.py"""

    def __init__(self, sidebar: SidebarWindow) -> None:
        self._sidebar = sidebar
        self._badge = 0
        self._icon = pystray.Icon(
            "et-office", icon=self._draw_icon(0), title="ET Office",
            menu=pystray.Menu(
                pystray.MenuItem("เปิด/หุบ Sidebar", self._toggle, default=True),
                pystray.MenuItem("ออกจาก ET Office", self._exit),
            ))

    def start(self) -> None:
        threading.Thread(target=self._icon.run, daemon=True).start()

    def set_badge(self, count: int) -> None:
        if count == self._badge:
            return
        self._badge = count
        self._icon.icon = self._draw_icon(count)

    def notify(self, title: str, message: str) -> None:
        try:
            self._icon.notify(message or " ", title)
        except Exception:
            pass  # notification เป็นของแถม — อย่าให้ล้ม host

    def _draw_icon(self, badge: int) -> Image.Image:
        from pathlib import Path
        custom = Path(__file__).parent / "assets" / "tray.png"
        if custom.exists():
            img = Image.open(custom).convert("RGBA").resize((64, 64))
        else:
            img = Image.new("RGBA", (64, 64), (7, 5, 15, 255))
            d = ImageDraw.Draw(img)
            d.rectangle([4, 4, 59, 59], outline=(224, 64, 251, 255), width=4)
            d.rectangle([16, 18, 46, 26], fill=(0, 229, 255, 255))   # E บน
            d.rectangle([16, 30, 38, 36], fill=(0, 229, 255, 255))   # E กลาง
            d.rectangle([16, 40, 46, 48], fill=(0, 229, 255, 255))   # E ล่าง
        if badge > 0:
            d = ImageDraw.Draw(img)
            d.ellipse([36, 34, 62, 60], fill=(255, 77, 166, 255))
            d.text((44, 38), str(min(badge, 9)), fill=(255, 255, 255, 255))
        return img

    def _toggle(self) -> None:
        # ส่งผ่าน daemon เส้นเดียวกับปุ่มบนหน้าเพจ — ทั้ง window และ CSS sync พร้อมกัน
        body = json.dumps({"type": "sidebar.toggle",
                           "data": {"expanded": not self._sidebar.expanded}}).encode()
        req = urllib.request.Request(DAEMON_HTTP + "/event", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=3)
        except Exception:
            self._sidebar.set_expanded(not self._sidebar.expanded)  # daemon down → ปรับเองตรง ๆ

    def _exit(self) -> None:
        self._icon.stop()
        if self._sidebar.window:
            self._sidebar.window.destroy()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-task", help="ส่ง task นี้ผ่าน input จริงหลังโหลด (QA M4-5)")
    parser.add_argument("--qa-toggle", action="store_true",
                        help="collapse แล้ว expand อัตโนมัติ (QA M4-3)")
    parser.add_argument("--qa-settings", action="store_true",
                        help="เปิด settings panel อัตโนมัติ (QA M4-6)")
    args = parser.parse_args()

    params = {}
    if args.qa_task:
        params["qa_task"] = args.qa_task
    if args.qa_toggle:
        params["qa_toggle"] = "1"
    if args.qa_settings:
        params["qa_settings"] = "1"
    url = DAEMON_URL + ("?" + urllib.parse.urlencode(params) if params else "")

    sb = SidebarWindow()
    sb.window = webview.create_window(
        "ET Office Sidebar",
        url=url,
        width=EXPANDED_W, height=900,
        min_size=(COLLAPSED_W, 200),  # default 200x100 จะ clamp ความกว้างตอนหุบ
        frameless=True, resizable=False, on_top=False,
    )

    tray = Tray(sb)

    def after_start() -> None:
        sb._snap()
        tray.start()
        threading.Thread(target=sb.listen_toggle, args=(tray,), daemon=True).start()

    webview.start(after_start)


if __name__ == "__main__":
    main()
