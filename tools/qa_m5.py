"""QA Gate M5 — release / clean-install pre-flight (M5-8)

ด่านสุดท้ายก่อนปล่อย v1.0 คือ "ลงเครื่องเปล่า Win10/Win11 ที่ไม่เคยมี dev tools"
(ดู docs/QA-M5-CHECKLIST.md — ต้องรันด้วยมือบนเครื่องจริง 2 ตัว)

สคริปต์นี้ทำ "พรีไฟลต์อัตโนมัติ" ที่จับ regression ของ packaging/asset/error-state
ซึ่งเป็นต้นเหตุที่ทำให้ clean install พังบ่อยที่สุด — รันได้โดยไม่ต้องมี daemon:

  python tools/qa_m5.py          → static checks (artifact, spec, error states, docs)
  python tools/qa_m5.py --full   → + ถ้า daemon รันอยู่: ตรวจ /health (ollama_ok ฯลฯ)

ผ่านครบ = ชุดไฟล์พร้อมเอาไป build/ปล่อย แล้วค่อยทำ checklist บนเครื่องเปล่าจริง
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # tools/ -> repo
BASE = "http://localhost:8797"

try:                                  # คอนโซล Windows (cp1252) พังกับข้อความไทย — บังคับ utf-8
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_results: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, info: str = "") -> None:
    _results.append((bool(ok), name, info))
    print(("PASS" if ok else "FAIL"), "-", name, (f"  [{info}]" if info else ""))


def warn(name: str, info: str = "") -> None:
    # ของแถม/ขึ้นกับสภาพแวดล้อม — ไม่ทำให้ gate ตก แต่เตือนให้เห็น
    _results.append((True, name, info))
    print("WARN", "-", name, (f"  [{info}]" if info else ""))


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


# --- A-8: icon ฝังครบ ---------------------------------------------------------
def check_icon() -> None:
    print("\n--- A-8 icon (.exe + tray) ---")
    ico = ROOT / "art-src" / "icon.ico"
    check("art-src/icon.ico มีอยู่", ico.is_file(),
          f"{ico.stat().st_size} bytes" if ico.is_file() else "รัน art-src/gen_app_icon.py")
    tray = ROOT / "sidebar" / "assets" / "tray.png"
    check("sidebar/assets/tray.png มีอยู่", tray.is_file())
    spec = read(ROOT / "installer" / "et-office.spec")
    check("spec ฝัง icon ครบทั้ง 3 EXE", spec.count("icon=ICON") == 3,
          f"พบ icon=ICON {spec.count('icon=ICON')} จุด")


# --- M5-3/M5-4: artifact + bundled data --------------------------------------
def check_artifact() -> None:
    print("\n--- M5-1..M5-4 artifact + bundle ---")
    spec = read(ROOT / "installer" / "et-office.spec")
    check("spec bundle sidebar/web", '"sidebar/web"' in spec)
    check("spec bundle daemon/roles", '"daemon/roles"' in spec)
    for f in ("launcher.py",):
        check(f"shell/{f} มีอยู่", (ROOT / "shell" / f).is_file())
    check("et-office.cmd (quick launcher) มีอยู่", (ROOT / "et-office.cmd").is_file())
    check("installer/install.ps1 มีอยู่", (ROOT / "installer" / "install.ps1").is_file())

    dist = ROOT / "dist" / "ET-Office"
    exes = ["ET-Office.exe", "et-office-daemon.exe", "et-office-sidebar.exe"]
    if dist.is_dir():
        for e in exes:
            check(f"dist/ET-Office/{e} (built)", (dist / e).is_file())
    else:
        warn("dist/ET-Office ยังไม่ได้ build", "รัน installer/build.ps1 ก่อนปล่อยจริง")


# --- M5-2: installer ครอบ clean machine --------------------------------------
def check_installer() -> None:
    print("\n--- M5-2 installer (clean machine) ---")
    ps = read(ROOT / "installer" / "install.ps1")
    check("installer ตรวจ WebView2 runtime", "WebView2" in ps or "EdgeWebView2" in ps)
    check("installer ตรวจ/ติดตั้ง Ollama", "ollama" in ps.lower())
    check("installer VRAM detect", "nvidia-smi" in ps)
    check("installer pull model", "pull" in ps)
    check("installer สร้าง shortcut", "CreateShortcut" in ps or ".lnk" in ps)


# --- M5-5: error / empty / loading states ------------------------------------
def check_error_states() -> None:
    print("\n--- M5-5 error/empty/loading states ---")
    html = read(ROOT / "sidebar" / "web" / "index.html")
    css = read(ROOT / "sidebar" / "web" / "style.css")
    js = read(ROOT / "sidebar" / "web" / "app.js")
    check("overlay daemon-down/connecting (HTML)", 'id="sys-overlay"' in html)
    check("ollama-warn banner (HTML)", 'id="ollama-warn"' in html)
    check("sys-overlay styled (CSS)", "#sys-overlay" in css and ".sys-banner" in css)
    check("showOverlay() เรียกตอน connecting + onclose",
          "showOverlay(" in js and js.count("showOverlay(") >= 3)
    check("checkOllama() ผูกกับ /health", "checkOllama" in js and "ollama_ok" in js)
    check("empty-state รายชื่อ agent ว่าง", "ยังไม่มี agent" in js)
    check("daemon /health คืน ollama_ok",
          "ollama_ok" in read(ROOT / "daemon" / "routes" / "system.py"))


# --- M5-7: เอกสารภาษาไทย + checklist -----------------------------------------
def check_docs() -> None:
    print("\n--- M5-7 docs + M5-8 checklist ---")
    readme = read(ROOT / "README.md")
    check("README.md มีอยู่", bool(readme), f"{len(readme)} ตัวอักษร")
    check("README มี setup/quick start", any(k in readme for k in
          ("Quick Start", "ติดตั้ง", "เริ่มต้น", "Setup")))
    chk = ROOT / "docs" / "QA-M5-CHECKLIST.md"
    check("docs/QA-M5-CHECKLIST.md (clean install) มีอยู่", chk.is_file())


# --- model map parity (install.ps1 vs daemon) --------------------------------
def check_model_parity() -> None:
    print("\n--- MODEL_MAP parity (informational) ---")
    ps = read(ROOT / "installer" / "install.ps1")
    adapter = read(ROOT / "daemon" / "adapters" / "llm_adapter.py")
    for tag in ("qwen3:8b", "qwen3:32b"):
        in_ps = tag in ps
        in_ad = tag in adapter
        if in_ps and in_ad:
            check(f"{tag} ตรงกันทั้ง installer + daemon", True)
        else:
            warn(f"{tag} ไม่ตรง", f"installer={in_ps} daemon={in_ad}")


# --- optional: daemon ที่รันอยู่ ---------------------------------------------
def check_live() -> None:
    print("\n--- live daemon (--full) ---")
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=5) as r:
            h = json.loads(r.read().decode() or "{}")
    except Exception as e:
        warn("daemon ไม่ได้รัน — ข้าม live checks", str(e)[:60])
        return
    check("/health status ok", h.get("status") == "ok")
    check("/health รายงาน ollama_ok", "ollama_ok" in h, f"ollama_ok={h.get('ollama_ok')}")
    if h.get("ollama_ok") is False:
        warn("Ollama ไม่ได้รัน", "banner เตือนใน sidebar ควรขึ้น (M5-5)")


def main() -> int:
    full = "--full" in sys.argv
    print("=== QA Gate M5 — release / clean-install pre-flight ===")
    check_icon()
    check_artifact()
    check_installer()
    check_error_states()
    check_docs()
    check_model_parity()
    if full:
        check_live()

    fails = [r for r in _results if not r[0]]
    total = len(_results)
    print(f"\n=== {total - len(fails)}/{total} ผ่าน ===")
    if fails:
        print("ตก:")
        for _, name, info in fails:
            print("  -", name, (f"[{info}]" if info else ""))
        print("\nแก้ให้ครบก่อน build/ปล่อย แล้วทำ docs/QA-M5-CHECKLIST.md บนเครื่องเปล่าจริง")
        return 1
    print("พรีไฟลต์ผ่าน — ไปต่อที่ clean-install บน Win10 + Win11 (docs/QA-M5-CHECKLIST.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
