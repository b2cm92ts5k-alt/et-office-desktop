"""ToolExecutor (M6-7) — เครื่องมือทำงานจริงของ agent ภายใต้ workspace sandbox

กฎเหล็ก:
- ทุก path ต้อง resolve แล้วอยู่ใต้ workspace เท่านั้น (กัน ../ traversal + absolute path)
- PowerShell รันด้วย cwd=workspace + timeout — แต่คำสั่งวิ่งออกนอก workspace ได้
  จึงต้องผ่าน permission gate ทุกครั้งเสมอ (M6-8 เป็นคนคุม ไม่ใช่ที่นี่)
- ทุก tool คืน string observation ให้ LLM อ่านต่อ — error คืนเป็นข้อความ ไม่ throw
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from .settings_store import settings_store

GH_API = "https://api.github.com"

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
    # GitHub (M9-4) — ต้องเชื่อม token + ตั้ง repo ใน Settings ก่อน, ทุก action ผ่าน permission gate
    "gh_list_issues":   {"args": ["state"],            "desc": "ดู issue/Task ใน GitHub repo (state: open/closed/all)"},
    "gh_create_issue":  {"args": ["title", "body"],    "desc": "สร้าง issue/Task ใหม่ใน GitHub repo"},
    "gh_comment_issue": {"args": ["number", "body"],   "desc": "คอมเมนต์/อัปเดต issue ตามเลข"},
    "gh_close_issue":   {"args": ["number"],           "desc": "ปิด issue ตามเลข"},
    # git (M9-5) — รันใน workspace, push ขึ้น remote ที่ตั้งไว้, ทุก action ผ่าน permission gate
    "git_status": {"args": [],          "desc": "ดูสถานะ git ใน workspace (branch + ไฟล์ที่เปลี่ยน)"},
    "git_diff":   {"args": [],          "desc": "ดูสรุปการเปลี่ยนแปลง (git diff --stat)"},
    "git_commit": {"args": ["message"], "desc": "git add -A แล้ว commit ใน workspace"},
    "git_push":   {"args": [],          "desc": "git push ขึ้น remote ที่ตั้งไว้"},
}


# M11-3 (§3.3) — preset whitelist แนะนำต่อ role (UI/hire เอาไปตั้ง allowed_tools ได้)
# ไม่ได้บังคับใช้เอง — เป็นแค่ค่าแนะนำ; การบังคับจริงดูที่ tool_allowed() + task_router
ROLE_TOOL_PRESETS: dict[str, list[str]] = {
    "coder":      ["read_file", "write_file", "list_dir", "mkdir", "move",
                   "git_status", "git_diff", "git_commit", "git_push"],
    "designer":   ["read_file", "write_file", "list_dir", "mkdir"],
    "researcher": ["read_file", "write_file", "list_dir", "fetch_url"],
    "producer":   ["read_file", "list_dir",
                   "gh_list_issues", "gh_create_issue", "gh_comment_issue", "gh_close_issue"],
}


def tool_allowed(tool: str, allowed_tools: list[str] | None) -> bool:
    """M11-3 — เช็ค whitelist ต่อ role ก่อนรัน tool

    ว่าง/None = อนุญาตทุก tool (backward compat กับ agent เดิมที่ไม่ได้ตั้ง).
    ตั้งรายการแล้ว = อนุญาตเฉพาะที่อยู่ในรายการ (เช่น designer เรียก git_push ไม่ได้).
    """
    if not allowed_tools:
        return True
    return tool in allowed_tools


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


def _gh_repo() -> str:
    repo = str(settings_store.get("github_repo") or "").strip()
    if not repo:
        raise WorkspaceError("ยังไม่ได้ตั้ง GitHub repo ใน Settings")
    return repo


def _gh_request(method: str, path: str, body: dict | None = None):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise WorkspaceError("ยังไม่ได้เชื่อม GitHub (ตั้ง token ใน Settings)")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        GH_API + path, data=data, method=method,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "User-Agent": "ET-Office/0.1", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode() or "{}")


def _execute_github(tool: str, args: dict) -> str:
    """GitHub tools (M9-4) — ไม่ต้องใช้ workspace, คุมด้วย permission gate"""
    repo = _gh_repo()
    try:
        if tool == "gh_list_issues":
            state = str(args.get("state", "open") or "open")
            issues = _gh_request("GET", f"/repos/{repo}/issues?state={state}&per_page=20")
            rows = [f"#{i['number']} [{i['state']}] {i['title']}"
                    for i in issues if "pull_request" not in i]
            return "\n".join(rows) or "(ไม่มี issue)"
        if tool == "gh_create_issue":
            title = str(args.get("title", "")).strip()
            if not title:
                return "ต้องมี title"
            r = _gh_request("POST", f"/repos/{repo}/issues",
                            {"title": title, "body": str(args.get("body", ""))})
            return f"สร้าง issue #{r['number']} แล้ว: {r.get('html_url', '')}"
        if tool == "gh_comment_issue":
            num = args.get("number")
            _gh_request("POST", f"/repos/{repo}/issues/{num}/comments",
                        {"body": str(args.get("body", ""))})
            return f"คอมเมนต์ที่ issue #{num} แล้ว"
        if tool == "gh_close_issue":
            num = args.get("number")
            _gh_request("PATCH", f"/repos/{repo}/issues/{num}", {"state": "closed"})
            return f"ปิด issue #{num} แล้ว"
        return f"ไม่รู้จัก github tool: {tool}"
    except WorkspaceError:
        raise
    except urllib.error.HTTPError as e:
        return f"GitHub error {e.code}: {_clip(e.read().decode(errors='replace'), 300)}"
    except Exception as exc:  # noqa: BLE001
        return f"github tool ล้มเหลว: {exc}"


def _git(git_args: list[str], root: Path) -> str:
    """รัน git ใน workspace (M9-5) — คืน stdout+stderr รวม (push ใช้ credential ของเครื่อง)"""
    r = subprocess.run(["git", *git_args], cwd=root, capture_output=True, timeout=PS_TIMEOUT_SEC)
    out = (r.stdout.decode("utf-8", errors="replace") + r.stderr.decode("utf-8", errors="replace")).strip()
    return _clip(out)


def execute(tool: str, args: dict) -> str:
    """รัน tool หนึ่งครั้ง — เรียกหลังผ่าน permission gate แล้วเท่านั้น"""
    if tool.startswith("gh_"):
        return _execute_github(tool, args)   # GitHub ไม่ผูกกับ workspace
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

        if tool == "git_status":
            return _git(["status", "--short", "--branch"], root) or "(working tree สะอาด)"

        if tool == "git_diff":
            return _git(["diff", "--stat"], root) or "(ไม่มีการเปลี่ยนแปลง)"

        if tool == "git_commit":
            msg = str(args.get("message", "")).strip()
            if not msg:
                return "ต้องมี message"
            _git(["add", "-A"], root)
            return _git(["commit", "-m", msg], root)

        if tool == "git_push":
            return _git(["push"], root)

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
    if tool == "gh_create_issue":
        return f"สร้าง GitHub issue: {args.get('title')}"
    if tool == "gh_comment_issue":
        return f"คอมเมนต์ GitHub issue #{args.get('number')}"
    if tool == "gh_close_issue":
        return f"ปิด GitHub issue #{args.get('number')}"
    if tool == "gh_list_issues":
        return f"ดู GitHub issues ({args.get('state', 'open')})"
    if tool == "git_commit":
        return f"git commit: {args.get('message')}"
    if tool == "git_push":
        return "git push ขึ้น remote"
    if tool == "git_status":
        return "ดู git status"
    if tool == "git_diff":
        return "ดู git diff"
    main_arg = args.get("path", args.get("url", ""))
    labels = {"list_dir": "ดูโฟลเดอร์", "read_file": "อ่านไฟล์",
              "mkdir": "สร้างโฟลเดอร์", "delete": "ลบ"}
    return f"{labels.get(tool, tool)} {main_arg}".strip()
