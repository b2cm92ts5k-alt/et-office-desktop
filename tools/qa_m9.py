"""QA Gate M9 — Terminal file-drop + GitHub/git integration (M9-1..M9-5)

รันแบบ import ตรง (ไม่ต้องมี daemon): python tools/qa_m9.py
ครอบคลุม: route wiring, tool registration, summarize coverage, git commit e2e (temp repo)

หมายเหตุ live ที่ทดสอบมือแล้ว (ไม่อยู่ในสคริปต์):
- drag-drop/ปุ่ม 📎 → _inbox → agent อ่านไฟล์ (verified ในแอปจริง)
- gh_* tools ยิง GitHub API ถูกรูปแบบ (ต้องใช้ PAT ที่เข้าถึง repo + github_repo ตั้งไว้)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root → import daemon

_results: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, info: str = "") -> None:
    _results.append((ok, name, info))
    print(("PASS" if ok else "FAIL"), "-", name, (f"  [{info}]" if info else ""))


def main() -> None:
    import daemon.main
    from daemon.services import tool_executor as TE

    print("--- M9-2/3/4 route wiring ---")
    paths = {getattr(r, "path", "") for r in daemon.main.app.routes}
    for p in ("/files/drop", "/settings/github", "/settings/github-repo", "/settings/onboarding"):
        check(f"route {p}", p in paths)

    print("\n--- M9-4/5 tool registration ---")
    gh = ["gh_list_issues", "gh_create_issue", "gh_comment_issue", "gh_close_issue"]
    git = ["git_status", "git_diff", "git_commit", "git_push"]
    for t in gh + git:
        check(f"TOOLS_SPEC has {t}", t in TE.TOOLS_SPEC)
    # summarize ต้องไม่ตกเป็น default (อ่านออกใน permission dialog)
    for t in ("gh_create_issue", "gh_close_issue", "git_commit", "git_push"):
        s = TE.summarize(t, {"title": "x", "number": "1", "message": "m"})
        check(f"summarize({t}) มีคำอธิบาย", bool(s) and t not in s)

    print("\n--- M9-4 GitHub guards ---")
    # ไม่มี repo ตั้งไว้ → _gh_repo ต้อง raise (กันยิงมั่ว)
    from daemon.services.settings_store import settings_store
    old = settings_store.get("github_repo")
    settings_store._values["github_repo"] = ""
    try:
        TE._gh_repo()
        check("ไม่ตั้ง repo → บล็อก", False)
    except TE.WorkspaceError:
        check("ไม่ตั้ง repo → บล็อก", True)
    finally:
        settings_store._values["github_repo"] = old

    print("\n--- M9-5 git commit e2e (temp repo) ---")
    d = Path(tempfile.mkdtemp())
    try:
        for c in (["init"], ["config", "user.email", "t@t.co"], ["config", "user.name", "qa"]):
            subprocess.run(["git", *c], cwd=d, capture_output=True)
        (d / "plan.md").write_text("qa", encoding="utf-8")
        TE._git(["add", "-A"], d)
        commit_out = TE._git(["commit", "-m", "qa m9"], d)
        check("git_commit สร้าง commit", "qa m9" in commit_out or "1 file" in commit_out, commit_out[:60])
        log = TE._git(["log", "--oneline"], d)
        check("git log เห็น commit", "qa m9" in log, log[:60])
    finally:
        shutil.rmtree(d, ignore_errors=True)

    passed = sum(1 for ok, _, _ in _results if ok)
    total = len(_results)
    print(f"\n=== M9 QA: {passed}/{total} PASS ===")
    if passed != total:
        print("FAILED:", [n for ok, n, _ in _results if not ok])
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
