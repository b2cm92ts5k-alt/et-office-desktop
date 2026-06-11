# ET Office Desktop Wallpaper

> 🏢 Cyberpunk Synthwave isometric AI agent office — รันเป็น **live desktop wallpaper** บน Windows
> ขับเคลื่อนด้วย **Ollama + Qwen** (local, ฟรี 100%) + **CrewAI** multi-agent framework

AI Agent ทีมงานเดินทำงาน ประชุม คุยกันเอง อยู่หลัง desktop icon ของคุณ — ข้อมูลไม่ออกนอกเครื่อง ไม่ต้องจ่าย subscription ใส่ API key เสริม Claude / Gemini / GPT ได้ per-agent

## Architecture

```
Godot 4 (wallpaper renderer)  ←─ WebSocket ─→  Python FastAPI Daemon  ←─→  CrewAI + Ollama
Sidebar UI (webview2)         ←─ HTTP/WS ───→       (source of truth)        Qwen (local default)
```

| Layer | Stack |
|---|---|
| Renderer | Godot 4.6+ (GDScript) + WorkerW wallpaper embed |
| Daemon | Python 3.12 + FastAPI + WebSocket hub (port 8797) |
| AI | CrewAI + Ollama (qwen3:8b default) / Claude / Gemini / OpenAI optional |
| Sidebar | HTML/CSS/JS + webview2 + pystray |

## Project Structure

```
godot/       Godot 4 project — wallpaper renderer (scenes, scripts, shaders, sprites)
daemon/      Python FastAPI server — agents, task router, proposals, settings
sidebar/     Sidebar UI (HTML/JS served by daemon)
shell/       Launcher — spawn daemon + Godot + sidebar
tools/       wallpaper.ps1 (WorkerW attach/detach)
installer/   install.ps1 (one-shot installer)
```

## Quick Start (dev)

```powershell
# 1. daemon
python -m venv .venv
.\.venv\Scripts\pip install -r daemon\requirements.txt
copy daemon\.env.example daemon\.env
uvicorn daemon.main:app --reload --port 8797

# 2. Ollama
ollama pull qwen3:8b

# 3. Godot — เปิด godot/ ด้วย Godot 4.6+
```

## Status

🚧 อยู่ระหว่างพัฒนา — ดู [Project Board](https://github.com/users/b2cm92ts5k-alt/projects/1)

## License

[MIT](LICENSE) — โปรเจคนี้เป็นส่วนหนึ่งของ ETLoLz AI Build series
