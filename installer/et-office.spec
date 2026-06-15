# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec (M5-3) — แพ็ค 3 exe ลง dist/ET-Office เดียว แชร์ _internal

  ET-Office.exe          launcher (console — เห็น log + Ctrl+C ปิดทั้งระบบ)
  et-office-daemon.exe   FastAPI daemon port 8797 (console — log uvicorn)
  et-office-sidebar.exe  pywebview sidebar + terminal + tray (no console)

จุดสำคัญ:
- onedir เท่านั้น — โค้ด daemon อ้าง path ด้วย __file__ (data/, roles/, .env,
  sidebar/web) ทุกอย่างจึง map ลง _internal/daemon/... ที่เขียนได้จริง
- bundle daemon/roles → สร้าง _internal/daemon/ ให้มีตัวตนจริงบนดิสก์
  (data dir / .env ใช้ mkdir(exist_ok=True) ที่ต้องมี parent อยู่ก่อน)
- litellm/crewai/tiktoken มี data files ที่ต้อง collect ไม่งั้นพังตอน import

build: powershell -ExecutionPolicy Bypass -File installer\\build.ps1
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent          # spec อยู่ใน installer/ → ROOT = repo
ICON = str(ROOT / "art-src" / "icon.ico")   # A-8 (gen: art-src/gen_app_icon.py)

daemon_datas = [
    (str(ROOT / "daemon" / "roles"), "daemon/roles"),
    (str(ROOT / "sidebar" / "web"), "sidebar/web"),
]
daemon_datas += collect_data_files("litellm")    # model_prices json ฯลฯ
daemon_datas += collect_data_files("crewai")     # translations/prompts json
daemon_hidden = [
    "tiktoken_ext", "tiktoken_ext.openai_public",   # namespace plugin — hook มองไม่เห็น
]

a_daemon = Analysis(
    [str(ROOT / "installer" / "entry_daemon.py")],
    pathex=[str(ROOT)],
    datas=daemon_datas,
    hiddenimports=daemon_hidden,
)
a_sidebar = Analysis([str(ROOT / "sidebar" / "host.py")], pathex=[str(ROOT)])
a_launcher = Analysis([str(ROOT / "shell" / "launcher.py")], pathex=[str(ROOT)])

exe_daemon = EXE(
    PYZ(a_daemon.pure), a_daemon.scripts, [],
    exclude_binaries=True, name="et-office-daemon", console=True, icon=ICON,
)
exe_sidebar = EXE(
    PYZ(a_sidebar.pure), a_sidebar.scripts, [],
    exclude_binaries=True, name="et-office-sidebar", console=False, icon=ICON,
)
exe_launcher = EXE(
    PYZ(a_launcher.pure), a_launcher.scripts, [],
    exclude_binaries=True, name="ET-Office", console=True, icon=ICON,
)

COLLECT(
    exe_daemon, a_daemon.binaries, a_daemon.datas,
    exe_sidebar, a_sidebar.binaries, a_sidebar.datas,
    exe_launcher, a_launcher.binaries, a_launcher.datas,
    name="ET-Office",
)
