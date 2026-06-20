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
import re
import subprocess
import time
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
    "web_search": {"args": ["query"],           "desc": "ค้นเว็บ คืน title+url+สรุปสั้น (เอา url ไป fetch_url ต่อ)"},
    "fetch_url":  {"args": ["url"],             "desc": "ดึงเนื้อหาจากเว็บ (GET, text เท่านั้น)"},
    # M17 — สร้างภาพ (ET Artist). model เลือกที่ gear (image_model); prompt อังกฤษได้ผลดีสุด
    "generate_image": {"args": ["prompt", "filename"],
                       "desc": "สร้างรูปจากคำอธิบาย (prompt) → เซฟ PNG ใน workspace/artwork/ (ใส่ n=1-4, aspect=1:1/16:9/9:16 ได้)"},
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
    "researcher": ["read_file", "write_file", "list_dir", "web_search", "fetch_url"],
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


def _web_search(query: str, n: int = 6) -> str:
    """ค้นเว็บ (M15-4) — มี BRAVE_API_KEY ใน env → Brave (สะอาด); ไม่งั้น DuckDuckGo keyless

    คืน text รายการ title + url + สรุปสั้น ให้ agent เลือก url ไป fetch_url ต่อ. ไม่เก็บ key ใน log.
    """
    import os
    import re
    import urllib.parse

    q = query.strip()
    if not q:
        return "ต้องมี query"
    key = os.environ.get("BRAVE_API_KEY", "").strip()
    try:
        if key:  # Brave Search API (optional) — JSON สะอาดกว่า
            url = "https://api.search.brave.com/res/v1/web/search?q=" + urllib.parse.quote(q) + f"&count={n}"
            req = urllib.request.Request(url, headers={
                "Accept": "application/json", "X-Subscription-Token": key, "User-Agent": "ET-Office/0.1"})
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_SEC) as r:
                data = json.loads(r.read().decode("utf-8", errors="replace"))
            items = [{"title": w.get("title", ""), "url": w.get("url", ""),
                      "snippet": re.sub("<[^>]+>", "", w.get("description", ""))}
                     for w in (data.get("web", {}).get("results", []) or [])[:n]]
        else:  # DuckDuckGo HTML (keyless) — ต้อง POST form (GET คืนแค่หน้าฟอร์ม)
            req = urllib.request.Request(
                "https://html.duckduckgo.com/html/",
                data=urllib.parse.urlencode({"q": q}).encode(),
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ET-Office/0.1",
                         "Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_SEC) as r:
                html = r.read(FETCH_CAP_BYTES).decode("utf-8", errors="replace")
            items = []
            hrefs = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S)
            snips = [re.sub("<[^>]+>", "", s).strip()
                     for s in re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.S)]
            for i, (href, title) in enumerate(hrefs[:n]):
                real = href
                if "uddg=" in href:
                    real = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg", [href])[0]
                items.append({"title": re.sub("<[^>]+>", "", title).strip(),
                              "url": real, "snippet": snips[i] if i < len(snips) else ""})
    except urllib.error.HTTPError as e:
        return f"web_search error {e.code} (ลองใหม่/เปลี่ยนคำค้น หรือใส่ BRAVE_API_KEY)"
    except Exception as exc:  # noqa: BLE001
        return f"web_search ล้มเหลว: {str(exc)[:120]}"
    if not items:
        return "ไม่พบผลลัพธ์ (ลองเปลี่ยนคำค้น)"
    return "\n".join(f"{i+1}. {it['title']}\n   {it['url']}\n   {_clip(it['snippet'], 200)}"
                     for i, it in enumerate(items))


# ── M17 image generation helpers ─────────────────────────────────────────────
def _img_ts() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _img_slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9ก-๙]+", "-", str(text or "").strip())[:40].strip("-").lower()
    return s or "image"


def image_target(agent) -> tuple[str, str, str] | None:
    """หา (provider, model, account_id) ของ tool generate_image (M17-3)

    agent ตั้ง image_model มา → ใช้ตามนั้น; ไม่งั้น default = provider ฟรีก่อน (gemini Nano Banana)
    แล้ว openai. ไม่มี credential ที่สร้างภาพได้เลย → None (tool คืนข้อความแนะนำ)
    """
    from ..adapters.image_adapter import DEFAULT_IMAGE_MODEL, IMAGE_PROVIDERS
    im = getattr(agent, "image_model", None) if agent is not None else None
    prov = getattr(im, "provider", "") if im is not None else ""
    if prov in IMAGE_PROVIDERS:
        model = getattr(im, "model", "") or DEFAULT_IMAGE_MODEL.get(prov, "")
        return (prov, model, getattr(im, "account_id", "") or "")
    from ..adapters.llm_adapter import available_cloud_providers
    avail = available_cloud_providers()
    for p in ("gemini", "openai"):   # ฟรีก่อน
        if p in IMAGE_PROVIDERS and avail.get(p):
            return (p, DEFAULT_IMAGE_MODEL[p], "")
    return None


def _emit_image(agent, paths: list[str], prompt: str, model: str) -> None:
    """ยิง WS event image.generated (M17-7) — โชว์ sidebar/Godot; พังก็ไม่ล้ม tool"""
    try:
        from .ws_manager import ws_manager
        ws_manager.emit({"type": "image.generated", "data": {
            "agent_id": getattr(agent, "id", "") if agent is not None else "",
            "paths": paths, "prompt": prompt[:120], "model": model}})
    except Exception:  # noqa: BLE001
        pass


def _generate_image(args: dict, root: Path, agent) -> str:
    from ..adapters import image_adapter
    from ..adapters.llm_adapter import _resolve_cloud_key
    target = image_target(agent)
    if not target:
        return "ยังไม่มี key ที่สร้างภาพได้ — เพิ่ม Gemini key (ฟรี) ที่ Settings → API Keys"
    provider, model, account_id = target
    key = _resolve_cloud_key(provider, account_id, "")
    if not key:
        return f"ยังไม่มี key ของ {provider} ที่ใช้สร้างภาพ — เพิ่มที่ Settings"
    prompt = str(args.get("prompt", "")).strip()
    if not prompt:
        return "ต้องมี prompt (คำอธิบายรูป — ภาษาอังกฤษได้ผลดีสุด)"
    try:
        n = int(args.get("n", 1) or 1)
    except (TypeError, ValueError):
        n = 1
    # M17-5 — model เสียเงิน + เกินงบ cloud ที่ตั้งไว้ → ไม่สร้าง (กันเงินรั่ว); ฟรีไม่บล็อก
    from ..services.cost_guard import cost_guard
    if cost_guard.image_price(provider, model) > 0 and cost_guard.over_budget():
        return ("เกินงบ cloud ที่ตั้งไว้ — สร้างรูปด้วย model เสียเงินไม่ได้ตอนนี้ "
                "(ปรับเพดานที่ Settings หรือสลับไป model ฟรี เช่น Nano Banana)")
    try:
        imgs = image_adapter.generate(provider, model, key, prompt,
                                      n=n, aspect=str(args.get("aspect", "1:1")))
    except image_adapter.ImageError as exc:
        return f"สร้างรูปไม่สำเร็จ: {exc}"
    art = _resolve("artwork", root)
    art.mkdir(parents=True, exist_ok=True)
    base = _img_slug(args.get("filename") or prompt)
    saved: list[str] = []
    stamp = _img_ts()
    for i, raw in enumerate(imgs):
        suffix = "" if len(imgs) == 1 else f"_{i + 1}"
        rel = f"artwork/{stamp}_{base}{suffix}.png"
        _resolve(rel, root).write_bytes(raw)
        saved.append(rel)
    usd = cost_guard.record_image(provider, model, len(saved))   # M17-5 — นับค่าใช้จ่ายต่อรูป
    _emit_image(agent, saved, prompt, f"{provider}/{model}")
    cost_note = f" · ~${round(usd, 3)}" if usd > 0 else " · ฟรี"
    return (f"สร้างรูปแล้ว {len(saved)} ไฟล์ (model: {provider}/{model}{cost_note}): "
            + ", ".join(saved))


def execute(tool: str, args: dict, agent=None) -> str:
    """รัน tool หนึ่งครั้ง — เรียกหลังผ่าน permission gate แล้วเท่านั้น

    agent (M17): AgentConfig ของผู้เรียก — generate_image ใช้หา image_model; tool อื่นไม่ใช้
    """
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

        if tool == "generate_image":
            return _generate_image(args, root, agent)

        if tool == "web_search":
            return _web_search(str(args.get("query", "")))

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
    if tool == "generate_image":
        return f"สร้างรูป: {str(args.get('prompt', ''))[:120]}"
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
