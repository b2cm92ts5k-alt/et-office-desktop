"""ToolExecutor (M6-7) — เครื่องมือทำงานจริงของ agent ภายใต้ workspace sandbox

กฎเหล็ก:
- ทุก path ต้อง resolve แล้วอยู่ใต้ workspace เท่านั้น (กัน ../ traversal + absolute path)
- PowerShell รันด้วย cwd=workspace + timeout — แต่คำสั่งวิ่งออกนอก workspace ได้
  จึงต้องผ่าน permission gate ทุกครั้งเสมอ (M6-8 เป็นคนคุม ไม่ใช่ที่นี่)
- ทุก tool คืน string observation ให้ LLM อ่านต่อ — error คืนเป็นข้อความ ไม่ throw
"""
from __future__ import annotations

import subprocess
import urllib.request
from pathlib import Path

from .settings_store import settings_store

READ_CAP = 30_000        # ตัวอักษรสูงสุดที่อ่านไฟล์/เว็บ/ผลคำสั่งคืนให้ LLM
PS_TIMEOUT_SEC = 60
FETCH_TIMEOUT_SEC = 20
FETCH_CAP_BYTES = 200_000

# คำอธิบาย tool — ใช้ทั้งใน system prompt (M6-9) และ permission dialog (M6-8)
TOOLS_SPEC = {
    "list_dir":   {"args": ["path"],            "desc": "ดูรายชื่อไฟล์/โฟลเดอร์ (path ว่าง = รากของ workspace)"},
    "read_file":  {"args": ["path"],            "desc": "อ่านเนื้อหาไฟล์ text"},
    "write_file": {"args": ["path", "content"], "desc": "สร้าง/เขียนทับไฟล์ (สร้างโฟลเดอร์ระหว่างทางให้)"},
    "mkdir":      {"args": ["path"],            "desc": "สร้างโฟลเดอร์"},
    "move":       {"args": ["src", "dst"],      "desc": "ย้าย/เปลี่ยนชื่อไฟล์หรือโฟลเดอร์"},
    "delete":     {"args": ["path"],            "desc": "ลบไฟล์ (โฟลเดอร์ต้องว่างถึงลบได้)"},
    "powershell": {"args": ["command"],         "desc": "รันคำสั่ง PowerShell ใน workspace"},
    "fetch_url":  {"args": ["url"],             "desc": "ดึงเนื้อหาจากเว็บ (GET, text เท่านั้น)"},
}


class WorkspaceError(Exception):
    pass


def workspace_root() -> Path:
    raw = str(settings_store.get("workspace_path") or "").strip()
    if not raw:
        raise WorkspaceError("ยังไม่ได้ตั้ง workspace — ตั้งได้ที่ Settings ใน sidebar")
    root = Path(raw).resolve()
    if not root.is_dir():
        raise WorkspaceError(f"workspace ไม่มีอยู่จริง: {root}")
    return root


def _resolve(rel: str, root: Path) -> Path:
    """path จาก LLM → absolute ใต้ workspace เท่านั้น"""
    p = (root / str(rel or "").strip().lstrip("/\\")).resolve()
    if p != root and root not in p.parents:
        raise WorkspaceError(f"path หลุดนอก workspace: {rel}")
    return p


def _clip(text: str, cap: int = READ_CAP) -> str:
    return text if len(text) <= cap else text[:cap] + f"\n…(ตัดที่ {cap} ตัวอักษร)"


def execute(tool: str, args: dict) -> str:
    """รัน tool หนึ่งครั้ง — เรียกหลังผ่าน permission gate แล้วเท่านั้น"""
    root = workspace_root()
    try:
        if tool == "list_dir":
            target = _resolve(args.get("path", ""), root)
            if not target.is_dir():
                return f"ไม่ใช่โฟลเดอร์: {args.get('path')}"
            rows = [f"{'[DIR] ' if e.is_dir() else ''}{e.name}"
                    for e in sorted(target.iterdir(), key=lambda e: (not e.is_dir(), e.name))]
            return "\n".join(rows) or "(โฟลเดอร์ว่าง)"

        if tool == "read_file":
            target = _resolve(args.get("path", ""), root)
            if not target.is_file():
                return f"ไม่พบไฟล์: {args.get('path')}"
            return _clip(target.read_text(encoding="utf-8", errors="replace"))

        if tool == "write_file":
            target = _resolve(args.get("path", ""), root)
            target.parent.mkdir(parents=True, exist_ok=True)
            content = str(args.get("content", ""))
            target.write_text(content, encoding="utf-8")
            return f"เขียนแล้ว: {target.relative_to(root)} ({len(content)} ตัวอักษร)"

        if tool == "mkdir":
            target = _resolve(args.get("path", ""), root)
            target.mkdir(parents=True, exist_ok=True)
            return f"สร้างโฟลเดอร์แล้ว: {target.relative_to(root)}"

        if tool == "move":
            src = _resolve(args.get("src", ""), root)
            dst = _resolve(args.get("dst", ""), root)
            if not src.exists():
                return f"ไม่พบต้นทาง: {args.get('src')}"
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
            return f"ย้ายแล้ว: {src.relative_to(root)} → {dst.relative_to(root)}"

        if tool == "delete":
            target = _resolve(args.get("path", ""), root)
            if target.is_dir():
                target.rmdir()  # ลบเฉพาะโฟลเดอร์ว่าง — กันลบยกโฟลเดอร์โดยไม่ตั้งใจ
                return f"ลบโฟลเดอร์ว่างแล้ว: {args.get('path')}"
            if target.is_file():
                target.unlink()
                return f"ลบไฟล์แล้ว: {args.get('path')}"
            return f"ไม่พบ: {args.get('path')}"

        if tool == "powershell":
            cmd = str(args.get("command", "")).strip()
            if not cmd:
                return "ไม่มีคำสั่ง"
            r = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd],
                cwd=root, capture_output=True, timeout=PS_TIMEOUT_SEC,
            )
            out = r.stdout.decode("utf-8", errors="replace")
            err = r.stderr.decode("utf-8", errors="replace")
            return _clip(f"exit={r.returncode}\n{out}" + (f"\nSTDERR:\n{err}" if err.strip() else ""))

        if tool == "fetch_url":
            url = str(args.get("url", "")).strip()
            if not url.startswith(("http://", "https://")):
                return "url ต้องขึ้นต้นด้วย http:// หรือ https://"
            req = urllib.request.Request(url, headers={"User-Agent": "ET-Office/0.1"})
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_SEC) as resp:
                body = resp.read(FETCH_CAP_BYTES)
            return _clip(body.decode("utf-8", errors="replace"))

        return f"ไม่รู้จัก tool: {tool} (ที่มี: {', '.join(TOOLS_SPEC)})"

    except WorkspaceError:
        raise
    except subprocess.TimeoutExpired:
        return f"คำสั่งเกิน {PS_TIMEOUT_SEC} วินาที — โดนตัด"
    except Exception as exc:
        return f"tool ล้มเหลว: {exc}"


def summarize(tool: str, args: dict) -> str:
    """สรุป action สั้น ๆ สำหรับ permission dialog + log (M6-8)"""
    if tool == "write_file":
        return f"เขียนไฟล์ {args.get('path')} ({len(str(args.get('content', '')))} ตัวอักษร)"
    if tool == "powershell":
        cmd = str(args.get("command", ""))
        return f"รัน PowerShell: {cmd[:160]}"
    if tool == "move":
        return f"ย้าย {args.get('src')} → {args.get('dst')}"
    if tool == "fetch_url":
        return f"เปิดเว็บ {args.get('url')}"
    main_arg = args.get("path", args.get("url", ""))
    labels = {"list_dir": "ดูโฟลเดอร์", "read_file": "อ่านไฟล์",
              "mkdir": "สร้างโฟลเดอร์", "delete": "ลบ"}
    return f"{labels.get(tool, tool)} {main_arg}".strip()
