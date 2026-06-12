"""PyInstaller entry ของ daemon (M5-3) — แทน `python -m uvicorn daemon.main:app`

ส่ง app object ตรง ๆ ไม่ใช่ import string — กัน uvicorn ไป import ซ้ำ
ผ่านกลไกที่หา module จาก filesystem ซึ่งไม่มีในตัว frozen exe
"""
import multiprocessing
import sys

import uvicorn

# pyinstaller + subprocess บน Windows: กัน child process วน import entry ซ้ำ
multiprocessing.freeze_support()

from daemon.main import app  # noqa: E402

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    uvicorn.run(app, host="127.0.0.1", port=8797)
