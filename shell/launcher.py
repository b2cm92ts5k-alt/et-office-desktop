"""ET Office Launcher (M5-1) — เปิด daemon + Godot + sidebar ครบในคำสั่งเดียว

ลำดับเปิด (ตาม DEV-RUN-GUIDE §2): daemon ก่อน → รอ /health → Godot + sidebar
ลำดับปิด (ตาม §7): sidebar → Godot ด้วย WM_CLOSE → daemon ท้ายสุด

กฎเหล็ก: Godot โหมด wallpaper ห้าม force kill — WM_CLOSE คือ trigger ให้
detach + คืน wallpaper เดิม + คืน Wallpaper Engine (M2-14) และหน้าต่าง Godot
ตอนเป็น wallpaper ถูก SetParent เข้า WorkerW แล้ว (ไม่ใช่ top-level) จึงต้อง
enumerate ผ่าน EnumChildWindows(GetDesktopWindow()) ถึงจะเจอ

ทุก process ผูกชะตากัน: ตัวใดตัวหนึ่งดับ (เช่นออกจาก tray ของ sidebar,
ปิดหน้าต่าง Godot) → launcher ปิดที่เหลือให้หมดแล้วจบ

รัน:  .venv\\Scripts\\python.exe shell\\launcher.py        (โหมด wallpaper จริง)
      shell\\launcher.py --window                          (Godot เป็น window ปกติ — dev/ถ่ายทำ)
      shell\\launcher.py --no-godot / --no-sidebar         (เปิดบางส่วน)
หรือดับเบิลคลิก et-office.cmd ที่ root repo
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from ctypes import wintypes
from pathlib import Path

# frozen = รันจาก exe ที่ PyInstaller แพ็ค (M5-3) — ทุกอย่างอยู่ข้างตัว launcher
FROZEN = bool(getattr(sys, "frozen", False))
EXE_DIR = Path(sys.executable).resolve().parent
REPO = EXE_DIR if FROZEN else Path(__file__).resolve().parent.parent
VENV_PY = REPO / ".venv" / "Scripts" / "python.exe"
DAEMON_EXE = EXE_DIR / "et-office-daemon.exe"
SIDEBAR_EXE = EXE_DIR / "et-office-sidebar.exe"
WALLPAPER_EXE = EXE_DIR / "et-office-wallpaper.exe"   # Godot export (M5-4)
# 127.0.0.1 ตรง ๆ — "localhost" ลอง ::1 ก่อนเสียเวลา ~2 วิ และ /health เอง
# ใช้อีก ~2 วิ (ping Ollama ทุกครั้ง) timeout จึงต้องเผื่อถึง 5 วิ
DAEMON_HEALTH = "http://127.0.0.1:8797/health"
GODOT_GLOB = "Godot_v*-stable_win64.exe"
WM_CLOSE = 0x0010
GODOT_CLOSE_GRACE_SEC = 12   # รอ detach + คืน wallpaper ก่อนยอม force
RUNFILE = REPO / "daemon" / "data" / "launcher_run.json"   # M12-3: pid ของ session ปัจจุบัน
APP_VERSION = "0.21.0"

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
user32 = ctypes.windll.user32


def log(msg: str) -> None:
    print(f"[ET OFFICE] {msg}", flush=True)


def banner() -> None:
    """M12-3 — header ทางการตอนเปิด"""
    print(flush=True)
    print("  ┌─────────────────────────────────────────────┐", flush=True)
    print(f"  │   ET OFFICE — AI agent desktop   v{APP_VERSION:<10}│", flush=True)
    print("  └─────────────────────────────────────────────┘", flush=True)


def image_name(pid: int) -> str:
    """ชื่อ exe ของ pid (lowercase) — '' ถ้าไม่ alive. ใช้กันฆ่า PID ที่ถูก recycle (M12-3)"""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, timeout=5).stdout.decode("utf-8", "replace")
        if f'"{pid}"' in out or f",{pid}," in out:
            return out.strip().split('","', 1)[0].strip('"').lower()
    except Exception:
        pass
    return ""


def find_godot() -> Path | None:
    """หา Godot exe — env GODOT_PATH ก่อน แล้วค่อย WinGet Packages (ทางเดียวกับ dev-godot.cmd)"""
    env = os.environ.get("GODOT_PATH", "")
    if env and Path(env).is_file():
        return Path(env)
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if base.is_dir():
        hits = sorted(base.rglob(GODOT_GLOB))
        if hits:
            return hits[-1]   # เวอร์ชันล่าสุด
    return None


def daemon_up(timeout: float = 5.0) -> bool:
    try:
        with urllib.request.urlopen(DAEMON_HEALTH, timeout=timeout) as r:
            return json.loads(r.read()).get("status") == "ok"
    except Exception:
        return False


def wait_daemon(timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if daemon_up():
            return True
        time.sleep(0.5)
    return False


def post_wm_close(pid: int) -> int:
    """ส่ง WM_CLOSE ไปทุก window ของ pid — เดินทั้ง top-level และ child ใต้ desktop
    (โหมด wallpaper Godot เป็น child ของ WorkerW ไม่โผล่ใน EnumWindows)"""
    sent = 0

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lparam):
        nonlocal sent
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid:
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            sent += 1
        return True

    user32.EnumWindows(cb, 0)
    user32.EnumChildWindows(user32.GetDesktopWindow(), cb, 0)
    return sent


class Launcher:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.daemon: subprocess.Popen | None = None
        self.daemon_owned = False     # daemon ที่รันอยู่ก่อนแล้วไม่ใช่ของเรา — ไม่ปิดให้
        self.godot: subprocess.Popen | None = None
        self.sidebar: subprocess.Popen | None = None

    # --- orphan cleanup (M12-3) -----------------------------------------
    def cleanup_orphans(self) -> None:
        """เก็บกวาด process ค้างจาก session ก่อนที่ออกไม่สะอาด (อ่านจาก run-file)

        ฆ่าเฉพาะ pid ใน run-file ที่ยัง alive และชื่อ exe ตรงที่คาด (กัน PID ถูก recycle
        ไปฆ่า process อื่น). godot → WM_CLOSE detach wallpaper ก่อน แล้วค่อย force.
        """
        if not RUNFILE.exists():
            return
        try:
            rec = json.loads(RUNFILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            rec = {}
        want = {"godot": ("godot", "wallpaper"), "sidebar": ("python", "sidebar"),
                "daemon": ("python", "daemon", "uvicorn")}
        cleaned = 0
        for name in ("godot", "sidebar", "daemon"):   # godot ก่อน (คืน wallpaper)
            pid = rec.get(name)
            if not isinstance(pid, int):
                continue
            img = image_name(pid)
            if not img or not any(s in img for s in want[name]):
                continue   # ดับไปแล้ว หรือ PID ถูก recycle เป็น process อื่น → ไม่แตะ
            log(f"พบ orphan {name} ค้างจากรอบก่อน (pid {pid}, {img}) → เก็บกวาด")
            if name == "godot":
                post_wm_close(pid)
                deadline = time.time() + GODOT_CLOSE_GRACE_SEC
                while time.time() < deadline and image_name(pid):
                    time.sleep(0.4)
            subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"], capture_output=True)
            cleaned += 1
        if cleaned:
            log(f"เก็บกวาด orphan {cleaned} ตัวเรียบร้อย")
        RUNFILE.unlink(missing_ok=True)

    def write_runfile(self) -> None:
        rec: dict[str, int] = {}
        if self.daemon_owned and self.daemon is not None:
            rec["daemon"] = self.daemon.pid
        if self.godot is not None:
            rec["godot"] = self.godot.pid
        if self.sidebar is not None:
            rec["sidebar"] = self.sidebar.pid
        try:
            RUNFILE.parent.mkdir(parents=True, exist_ok=True)
            RUNFILE.write_text(json.dumps(rec), encoding="utf-8")
        except OSError:
            pass

    # --- start -----------------------------------------------------------
    def start_daemon(self) -> bool:
        if daemon_up():
            log("daemon รันอยู่แล้ว (port 8797) — ใช้ตัวเดิม ไม่ปิดให้ตอนจบ")
            return True
        log("เปิด daemon (port 8797)...")
        cmd = ([str(DAEMON_EXE)] if FROZEN
               else [str(VENV_PY), "-m", "uvicorn", "daemon.main:app", "--port", "8797"])
        # process group แยก → ส่ง CTRL_BREAK ปิด uvicorn นุ่มนวลได้โดยไม่โดน console เรา
        self.daemon = subprocess.Popen(
            cmd, cwd=REPO, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        self.daemon_owned = True
        if not wait_daemon():
            log("daemon ไม่ตอบ /health ภายใน 30 วิ — ดู log ด้านบน (Ollama รันหรือยัง?)")
            return False
        log("daemon พร้อม ✓")
        return True

    def start_godot(self) -> bool:
        if FROZEN:
            # ตัว export standalone (M5-4) วางข้าง launcher — ไม่ต้องมี Godot บนเครื่อง
            if not WALLPAPER_EXE.is_file():
                log("ข้าม Godot — ยังไม่มี et-office-wallpaper.exe ข้าง launcher (M5-4)")
                return True
            cmd = [str(WALLPAPER_EXE)]
        else:
            godot = find_godot()
            if godot is None:
                log("ไม่พบ Godot — ติดตั้ง: winget install GodotEngine.GodotEngine "
                    "หรือตั้ง env GODOT_PATH ชี้ไปที่ exe")
                return False
            cmd = [str(godot), "--path", str(REPO / "godot")]
        if not self.args.window:
            cmd += ["--", "--wallpaper"]
        log(f"เปิด Godot ({'window' if self.args.window else 'wallpaper'} mode)...")
        self.godot = subprocess.Popen(cmd, cwd=REPO)
        return True

    def start_sidebar(self) -> bool:
        log("เปิด sidebar + terminal...")
        cmd = ([str(SIDEBAR_EXE)] if FROZEN
               else [str(VENV_PY), str(REPO / "sidebar" / "host.py")])
        self.sidebar = subprocess.Popen(cmd, cwd=REPO)
        return True

    # --- supervise --------------------------------------------------------
    def watch(self) -> str:
        """block จนกว่า process ใดตัวหนึ่งจบ — คืนชื่อตัวที่จบก่อน"""
        while True:
            for name, proc in (("sidebar", self.sidebar), ("godot", self.godot),
                               ("daemon", self.daemon)):
                if proc is not None and proc.poll() is not None:
                    return name
            time.sleep(1)

    # --- shutdown ---------------------------------------------------------
    def shutdown(self) -> None:
        # 1) sidebar — ปิดเฉย ๆ ได้ (terminal geometry save ตอน hide/move อยู่แล้ว)
        if self.sidebar is not None and self.sidebar.poll() is None:
            log("ปิด sidebar...")
            self.sidebar.terminate()
            try:
                self.sidebar.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.sidebar.kill()

        # 2) Godot — WM_CLOSE เท่านั้น (detach wallpaper + คืน Wallpaper Engine)
        if self.godot is not None and self.godot.poll() is None:
            log("ปิด Godot ด้วย WM_CLOSE (รอ detach wallpaper)...")
            post_wm_close(self.godot.pid)
            deadline = time.time() + GODOT_CLOSE_GRACE_SEC
            while time.time() < deadline and self.godot.poll() is None:
                time.sleep(0.5)
            if self.godot.poll() is None:
                log("⚠ Godot ไม่ตอบ WM_CLOSE — force kill (ถ้า desktop ค้าง: "
                    "คลิกขวา desktop → Refresh หรือตั้ง wallpaper ใหม่)")
                self.godot.kill()

        # 3) daemon ท้ายสุด — CTRL_BREAK ให้ uvicorn ปิดนุ่มนวล
        if self.daemon_owned and self.daemon is not None and self.daemon.poll() is None:
            log("ปิด daemon...")
            try:
                self.daemon.send_signal(signal.CTRL_BREAK_EVENT)
                self.daemon.wait(timeout=8)
            except (subprocess.TimeoutExpired, OSError):
                self.daemon.terminate()
        RUNFILE.unlink(missing_ok=True)   # M12-3 — ออกสะอาด → ไม่มี orphan ค้าง
        log("ปิดครบทุก process แล้ว")

    # --- main -------------------------------------------------------------
    def run(self) -> int:
        if not FROZEN and not VENV_PY.is_file():
            log(".venv ไม่พบ — ดู Quick Start ใน README.md")
            return 1
        banner()                 # M12-3
        self.cleanup_orphans()   # M12-3 — เก็บกวาด process ค้างจากรอบก่อนก่อนเริ่มใหม่
        # M7-8 belt-and-suspenders: บังคับ Ollama โหลด local model ได้ตัวเดียว/ไม่ขนาน
        # การันตีหลักมาจาก "ทุก agent ใช้ active tag เดียว" อยู่แล้ว — env นี้กันเคสตัวค้าง
        # ตอนสลับ (มีผลเฉพาะถ้า Ollama ถูกสตาร์ตใน/สืบทอด environment นี้)
        os.environ.setdefault("OLLAMA_MAX_LOADED_MODELS", "1")
        os.environ.setdefault("OLLAMA_NUM_PARALLEL", "1")
        if not self.start_daemon():
            self.shutdown()
            return 1
        try:
            if not self.args.no_godot and not self.start_godot():
                self.shutdown()
                return 1
            if not self.args.no_sidebar:
                self.start_sidebar()
            self.write_runfile()   # M12-3 — บันทึก pid เผื่อรอบหน้าต้องเก็บกวาด
            log("พร้อมทำงาน — ปิดทั้งหมด: ปุ่ม ⏻/พิมพ์ /exit ใน sidebar · Ctrl+C ที่นี่ · tray ET · ปิดหน้าต่าง Godot")
            first = self.watch()
            log(f"{first} จบการทำงาน → ปิดที่เหลือทั้งหมด")
        except KeyboardInterrupt:
            print(flush=True)
            log("Ctrl+C → ปิดทั้งหมด")
        finally:
            self.shutdown()
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ET Office launcher (M5-1)")
    parser.add_argument("--window", action="store_true",
                        help="Godot เป็น window ปกติ ไม่ฝัง wallpaper (dev/ถ่ายทำ)")
    parser.add_argument("--no-godot", action="store_true", help="ไม่เปิด Godot")
    parser.add_argument("--no-sidebar", action="store_true", help="ไม่เปิด sidebar")
    return Launcher(parser.parse_args()).run()


if __name__ == "__main__":
    sys.exit(main())
