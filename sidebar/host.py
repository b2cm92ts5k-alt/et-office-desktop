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

import webview
from websockets.sync.client import connect as ws_connect

DAEMON_URL = "http://localhost:8797/sidebar/index.html"
DAEMON_WS = "ws://localhost:8797/ws"
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

    def listen_toggle(self) -> None:
        """WS client เล็ก ๆ — รอ event sidebar.toggle จาก daemon แล้วปรับหน้าต่าง"""
        while True:
            try:
                with ws_connect(DAEMON_WS) as ws:
                    while True:
                        msg = json.loads(ws.recv())
                        if msg.get("replay"):
                            continue
                        if msg.get("type") == "sidebar.toggle":
                            self.set_expanded(bool(msg.get("data", {}).get("expanded", True)))
            except Exception:
                import time
                time.sleep(3)  # daemon หาย → รอแล้วต่อใหม่


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-task", help="ส่ง task นี้ผ่าน input จริงหลังโหลด (QA M4-5)")
    parser.add_argument("--qa-toggle", action="store_true",
                        help="collapse แล้ว expand อัตโนมัติ (QA M4-3)")
    args = parser.parse_args()

    params = {}
    if args.qa_task:
        params["qa_task"] = args.qa_task
    if args.qa_toggle:
        params["qa_toggle"] = "1"
    url = DAEMON_URL + ("?" + urllib.parse.urlencode(params) if params else "")

    sb = SidebarWindow()
    sb.window = webview.create_window(
        "ET Office Sidebar",
        url=url,
        width=EXPANDED_W, height=900,
        min_size=(COLLAPSED_W, 200),  # default 200x100 จะ clamp ความกว้างตอนหุบ
        frameless=True, resizable=False, on_top=False,
    )

    def after_start() -> None:
        sb._snap()
        threading.Thread(target=sb.listen_toggle, daemon=True).start()

    webview.start(after_start)


if __name__ == "__main__":
    main()
