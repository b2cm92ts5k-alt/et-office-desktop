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
import time
import urllib.parse
import urllib.request
from pathlib import Path

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

# Terminal Chat หน้าต่างแยก (M6-4/M6-5)
TERMINAL_URL = "http://localhost:8797/sidebar/terminal.html"
TERMINAL_DEFAULT_W, TERMINAL_DEFAULT_H = 420, 380
TERMINAL_MIN = (300, 220)   # ต้องตรงกับ MIN_W/MIN_H ใน terminal.js
STATE_PATH = Path(__file__).parent / "data" / "ui_state.json"


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

    def listen_toggle(self, tray: "Tray | None" = None,
                      term: "TerminalWindow | None" = None) -> None:
        """WS client เล็ก ๆ — sidebar.toggle → resize ทั้งสองหน้าต่าง (M6-5),
        terminal.resize → ปรับขนาดหน้าต่าง terminal (M6-4),
        agent.status → tray badge, task/proposal → notification toast (M4-9)"""
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
                            expanded = bool(data.get("expanded", True))
                            self.set_expanded(expanded)
                            if term:
                                term.set_visible(expanded)
                        elif mtype == "terminal.resize":
                            if term:
                                term.resize(data.get("w", TERMINAL_DEFAULT_W),
                                            data.get("h", TERMINAL_DEFAULT_H))
                        elif tray is None:
                            continue
                        elif mtype == "permission.request":
                            tray.notify("🔐 ทีมขออนุญาต",
                                        _trim(data.get("summary", ""), 120))
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
                        elif mtype == "wallpaper.conflict":
                            apps = ", ".join(data.get("apps", []))
                            tray.notify(
                                "⏸ pause wallpaper app ให้แล้ว" if data.get("paused")
                                else "⚠ wallpaper app ชนกัน",
                                f"{apps} — ET Office จัดการให้แล้ว" if data.get("paused")
                                else f"กรุณาปิด {apps} ก่อนใช้ ET Office")
            except Exception:
                import time
                time.sleep(3)  # daemon หาย → รอแล้วต่อใหม่


def _trim(s: str, n: int) -> str:
    s = " ".join(str(s or "").split())
    return s[:n] + "…" if len(s) > n else s


class TerminalWindow:
    """Terminal Chat แยกหน้าต่าง OS-level (M6-4) + จำตำแหน่ง/ขนาดข้าม session (M6-5)
    ลากย้ายอิสระทุกจุดบนจอ — collapse/expand ตาม sidebar.toggle พร้อม panel หลัก"""

    def __init__(self) -> None:
        self.window: webview.Window | None = None
        self._last_save = 0.0
        self._geo = self._load()

    def _load(self) -> dict:
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8")).get("terminal", {})
        except Exception:
            return {}

    def initial_rect(self) -> tuple[int, int, int, int]:
        """ตำแหน่ง+ขนาดตอนเปิด — ค่าที่จำไว้ (clamp กลับเข้าจอเผื่อจอเปลี่ยน) หรือ default
        มุมล่างขวาข้าง sidebar"""
        screen = webview.screens[0]
        w = max(TERMINAL_MIN[0], min(int(self._geo.get("w", TERMINAL_DEFAULT_W)), screen.width))
        h = max(TERMINAL_MIN[1],
                min(int(self._geo.get("h", TERMINAL_DEFAULT_H)), screen.height - TASKBAR_H))
        default_x = screen.width - EXPANDED_W - w - 12
        default_y = screen.height - TASKBAR_H - h - 12
        x = int(self._geo.get("x", default_x))
        y = int(self._geo.get("y", default_y))
        x = max(0, min(x, screen.width - TERMINAL_MIN[0]))
        y = max(0, min(y, screen.height - TASKBAR_H - TERMINAL_MIN[1]))
        return x, y, w, h

    def save(self, throttle: bool = False) -> None:
        if not self.window:
            return
        now = time.monotonic()
        if throttle and now - self._last_save < 1.0:
            return
        self._last_save = now
        try:
            STATE_PATH.parent.mkdir(exist_ok=True)
            STATE_PATH.write_text(json.dumps({"terminal": {
                "x": self.window.x, "y": self.window.y,
                "w": self.window.width, "h": self.window.height,
            }}), encoding="utf-8")
        except Exception:
            pass  # state เป็นของแถม — อย่าให้ host ล้ม

    def restore_geometry(self) -> None:
        """create_window ตั้ง Size ตอนยังมี frame แล้วค่อยถอดเป็น frameless —
        ขนาดจริงเลยหดเท่าขอบ window (~16×39px) ทุกครั้งที่เปิด (QA M6-10 จับได้)
        จึง enforce ขนาด+ตำแหน่งที่จำไว้ซ้ำหลัง start ซึ่ง resize/move
        ทำงานบนหน้าต่าง frameless แล้ว หน่วยตรงกับที่ save ไว้"""
        if not self.window:
            return
        x, y, w, h = self.initial_rect()
        self.window.resize(w, h)
        self.window.move(x, y)

    def set_visible(self, on: bool) -> None:
        if not self.window:
            return
        if on:
            self.window.show()   # โผล่กลับตำแหน่ง+ขนาดเดิม
        else:
            self.save()
            self.window.hide()

    def resize(self, w, h) -> None:
        if not self.window:
            return
        screen = webview.screens[0]
        w = max(TERMINAL_MIN[0], min(int(w), screen.width))
        h = max(TERMINAL_MIN[1], min(int(h), screen.height))
        self.window.resize(w, h)
        self.save(throttle=True)


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
        for w in list(webview.windows):  # ปิดทั้ง sidebar + terminal (M6-4)
            try:
                w.destroy()
            except Exception:
                pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-task", help="ส่ง task นี้ผ่าน input จริงหลังโหลด (QA M4-5)")
    parser.add_argument("--qa-toggle", action="store_true",
                        help="collapse แล้ว expand อัตโนมัติ (QA M4-3)")
    parser.add_argument("--qa-settings", action="store_true",
                        help="เปิด settings panel อัตโนมัติ (QA M4-6)")
    args = parser.parse_args()

    cache_bust = str(int(time.time()))  # กัน WebView2 cache หน้าเก่า — โหลดสดทุก launch
    params = {"v": cache_bust}
    if args.qa_toggle:
        params["qa_toggle"] = "1"
    if args.qa_settings:
        params["qa_settings"] = "1"
    url = DAEMON_URL + "?" + urllib.parse.urlencode(params)
    # qa_task ส่งให้หน้าต่าง terminal — input ย้ายไปอยู่ที่นั่นแล้ว (M6-4)
    term_params = {"v": cache_bust}
    if args.qa_task:
        term_params["qa_task"] = args.qa_task
    term_url = TERMINAL_URL + "?" + urllib.parse.urlencode(term_params)

    sb = SidebarWindow()
    sb.window = webview.create_window(
        "ET Office Sidebar",
        url=url,
        width=EXPANDED_W, height=900,
        min_size=(COLLAPSED_W, 200),  # default 200x100 จะ clamp ความกว้างตอนหุบ
        frameless=True, resizable=False, on_top=False,
    )

    term = TerminalWindow()
    tx, ty, tw, th = term.initial_rect()
    term.window = webview.create_window(
        "ET Terminal",
        url=term_url,
        x=tx, y=ty, width=tw, height=th,
        min_size=TERMINAL_MIN,
        frameless=True, resizable=True, on_top=False,
    )
    # จำตำแหน่ง/ขนาดเมื่อ user ลากหรือ resize (M6-5) — event ชื่อต่างกันตามเวอร์ชัน pywebview
    for ev_name in ("moved", "resized", "closing"):
        ev = getattr(term.window.events, ev_name, None)
        if ev is not None:
            ev += (lambda *a, **k: term.save(throttle=True))

    tray = Tray(sb)

    def after_start() -> None:
        sb._snap()
        term.restore_geometry()
        tray.start()
        threading.Thread(target=sb.listen_toggle, args=(tray, term), daemon=True).start()

    # private_mode=False — เก็บ localStorage ข้ามรอบ (ปิด-เปิดแล้ว state คืนได้, M4-11)
    # ALLOW_DOWNLOADS — ปุ่มดาวน์โหลด template spritesheet ใน hire dialog (M6-2 v2)
    # DRAG_REGION_DIRECT_TARGET_ONLY — ให้ปุ่มบน header ของ terminal คลิกได้ ไม่โดนลากแทน
    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.settings["DRAG_REGION_DIRECT_TARGET_ONLY"] = True
    webview.start(after_start, private_mode=False)


if __name__ == "__main__":
    main()
