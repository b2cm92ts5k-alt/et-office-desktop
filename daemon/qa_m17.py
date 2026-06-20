"""M17-9 QA Gate — Image Generation (ET Artist)

รัน offline: mock image_adapter.generate + key resolver (ไม่ยิง API จริง) แล้วเรียก
handler ตรง ๆ ครอบ flow: adapter dispatch · generate_image tool (เซฟ workspace) ·
image_target default · /models/available?kind=image · cost per-image + over-budget ·
permission spec · /files/raw serve.
รัน: .venv\\Scripts\\python.exe daemon\\qa_m17.py
"""
from __future__ import annotations

import base64
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daemon.adapters import image_adapter, llm_adapter  # noqa: E402
from daemon.models.schemas import AgentConfig, LLMConfig  # noqa: E402
from daemon.routes import files as files_route  # noqa: E402
from daemon.routes import models as M  # noqa: E402
from daemon.services import tool_executor as TE  # noqa: E402
from daemon.services.account_store import account_store  # noqa: E402
from daemon.services.cost_guard import cost_guard  # noqa: E402
from daemon.services.settings_store import settings_store  # noqa: E402

_FAILS: list[str] = []


def check(name: str, cond: bool) -> None:
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        _FAILS.append(name)


def _mi(i, k, **kw):
    return {"id": i, "label": kw.get("l", i), "kind": k, "ctx": None,
            "price_in": kw.get("pi"), "price_out": kw.get("po")}


def main() -> int:
    PNG = base64.b64encode(b"\x89PNG_fake").decode()
    # mock backends (ไม่ยิงเน็ต) ผ่าน _post_json + key resolver
    def fake_post(url, headers, body, timeout=120):
        if ":predict" in url:
            return {"predictions": [{"bytesBase64Encoded": PNG}] * body["parameters"]["sampleCount"]}
        if ":generateContent" in url:
            return {"candidates": [{"content": {"parts": [{"inline_data": {"data": PNG}}]}}]}
        if "openai" in url:
            return {"data": [{"b64_json": PNG} for _ in range(body["n"])]}
        return {}
    image_adapter._post_json = fake_post
    llm_adapter._resolve_cloud_key = lambda *a, **k: "KEY"

    tmp = tempfile.mkdtemp()
    old_ws = settings_store.get("workspace_path")
    settings_store.update({"workspace_path": tmp})
    for a in list(account_store.all_public()):
        if a["label"].startswith("M17QA"):
            account_store.delete(a["id"])
    gem_id = None
    try:
        # 1) adapter dispatch (nano vs imagen vs openai) + clamp + errors
        check("adapter gemini nano (generateContent)", len(image_adapter.generate("gemini", "gemini-2.5-flash-image", "K", "cat", n=2)) == 2)
        check("adapter gemini imagen (predict)", len(image_adapter.generate("gemini", "imagen-4.0-generate-001", "K", "dog", n=3)) == 3)
        check("adapter openai + clamp n<=4", len(image_adapter.generate("openai", "gpt-image-1", "K", "x", n=9)) == 4)
        check("adapter openrouter = v1 stub", _raises(lambda: image_adapter.generate("openrouter", "x", "K", "y")))
        check("adapter no-key / empty prompt error", _raises(lambda: image_adapter.generate("gemini", "m", "", "y")) and _raises(lambda: image_adapter.generate("gemini", "m", "K", "  ")))

        # 2) generate_image tool → เซฟ workspace/artwork + observation
        artist = AgentConfig(name="ET Artist", role="artist",
                             image_model=LLMConfig(provider="gemini", model="gemini-2.5-flash-image"))
        obs = TE.execute("generate_image", {"prompt": "neon city", "n": 2}, artist)
        files = sorted((Path(tmp) / "artwork").glob("*.png"))
        check("tool: เซฟ 2 ไฟล์ใน artwork/", len(files) == 2)
        check("tool: observation บอก model + ฟรี", "gemini-2.5-flash-image" in obs and "ฟรี" in obs)

        # 3) image_target default (ไม่มี image_model → gemini ฟรีก่อน)
        llm_adapter.available_cloud_providers = lambda: {"gemini": True, "openai": True}
        tgt = TE.image_target(AgentConfig(name="x", role="y"))
        check("image_target default = gemini Nano Banana (ฟรี)", tgt == ("gemini", "gemini-2.5-flash-image", ""))
        llm_adapter.available_cloud_providers = lambda: {"gemini": False, "openai": False}
        check("image_target ไม่มี cred → None", TE.image_target(AgentConfig(name="x", role="y")) is None)

        # 4) /models/available?kind=image
        gem_id = account_store.add_api_key("gemini", "M17QA", "k",
            [_mi("gemini-2.5-flash-image", "image", l="Nano Banana"),
             _mi("imagen-4.0-generate-001", "image", l="Imagen 4"),
             _mi("gemini-2.5-flash", "chat")])["id"]
        iopts = {o["model"]: o for o in M.available(kind="image")["options"] if o["provider"] == "gemini"}
        check("kind=image: image-kind ปรากฏ", {"gemini-2.5-flash-image", "imagen-4.0-generate-001"} <= set(iopts))
        check("kind=image: chat ไม่ปน", "gemini-2.5-flash" not in iopts)
        check("kind=image: ป้ายฟรี + selectable", "ฟรี" in iopts["gemini-2.5-flash-image"]["label"] and iopts["gemini-2.5-flash-image"]["selectable"])

        # 5) cost per-image + over-budget block (paid)
        check("cost: gemini ฟรี = 0", cost_guard.image_price("gemini", "gemini-2.5-flash-image") == 0.0)
        check("cost: openai gpt-image-1 > 0", cost_guard.image_price("openai", "gpt-image-1") == 0.04)
        paid = AgentConfig(name="P", role="artist", image_model=LLMConfig(provider="openai", model="gpt-image-1"))
        cost_guard.record_image("openai", "gpt-image-1", 1)   # ใช้เงินไปแล้ว (เกิน cap ต่ำ ๆ)
        settings_store.update({"cost_guard_enabled": True, "cost_daily_usd": 0.001})
        check("paid + เกินงบ → บล็อก", "เกินงบ" in TE.execute("generate_image", {"prompt": "z"}, paid))
        check("free ไม่บล็อกแม้เกินงบ", "สร้างรูปแล้ว" in TE.execute("generate_image", {"prompt": "z"}, artist))
        settings_store.update({"cost_guard_enabled": False, "cost_daily_usd": 0})

        # 6) permission/spec + role preset
        check("generate_image อยู่ใน TOOLS_SPEC", "generate_image" in TE.TOOLS_SPEC)
        check("summarize generate_image", TE.summarize("generate_image", {"prompt": "hi"}).startswith("สร้างรูป"))
        check("artist preset มี generate_image", "generate_image" in TE.ROLE_TOOL_PRESETS["artist"])
        check("tool_allowed: artist เรียก generate_image ได้", TE.tool_allowed("generate_image", TE.ROLE_TOOL_PRESETS["artist"]))

        # 7) /files/raw serve รูปที่เซฟ
        rel = files[0].relative_to(Path(tmp)).as_posix()
        resp = files_route.raw_file(rel)
        check("/files/raw serve ไฟล์ที่เซฟ", Path(getattr(resp, "path", "")).resolve() == files[0].resolve())
        check("/files/raw กัน path นอก workspace", _raises(lambda: files_route.raw_file("../secret.txt")))
    finally:
        if gem_id:
            account_store.delete(gem_id)
        settings_store.update({"workspace_path": old_ws or "", "cost_guard_enabled": False, "cost_daily_usd": 0})

    print()
    if _FAILS:
        print(f"M17-9 QA: {len(_FAILS)} FAILED -> {_FAILS}")
        return 1
    print("M17-9 QA: ALL PASSED")
    return 0


def _raises(fn) -> bool:
    try:
        fn()
        return False
    except Exception:
        return True


if __name__ == "__main__":
    sys.exit(main())
