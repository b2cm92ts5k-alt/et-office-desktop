"""M16-9 QA Gate — Dynamic Cloud Models & Provider Expansion

รันแบบ offline: mock validate_cloud_key (ไม่ยิง network จริง) แล้วเรียก route handler ตรง ๆ
ครอบ flow: add key→persist · /models/available (chat-only/all) · refresh diff · routing · pricing.
รัน: .venv\\Scripts\\python.exe daemon\\qa_m16.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daemon.adapters import llm_adapter as L  # noqa: E402
from daemon.models.schemas import LLMConfig  # noqa: E402
from daemon.routes import accounts as A  # noqa: E402
from daemon.routes import models as M  # noqa: E402
from daemon.services.account_store import account_store  # noqa: E402

_FAILS: list[str] = []


def check(name: str, cond: bool) -> None:
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        _FAILS.append(name)


# canned model list ต่อ provider (mutable — refresh test แก้ได้) ; ใช้ ModelInfo จริงผ่าน normalize
def mi(i, k, **kw):
    return {"id": i, "label": kw.get("label", i), "kind": k,
            "ctx": kw.get("ctx"), "price_in": kw.get("pi"), "price_out": kw.get("po")}


CANNED: dict[str, list[dict]] = {
    "gemini": [mi("gemini-2.5-flash", "chat"), mi("gemini-3-flash", "chat", label="Gemini 3 Flash"),
               mi("text-embedding-004", "embed"), mi("veo-2", "video")],
    "openrouter": [mi("anthropic/claude-3.5-sonnet", "chat", pi=3.0, po=15.0, ctx=200000),
                   mi("black-forest-labs/flux", "image")],
    "github": [mi("openai/gpt-4o", "chat"), mi("cohere/embed-v3", "embed")],
}


def fake_validate(provider: str, key: str, timeout: int = 12) -> dict:
    return {"ok": True, "models": list(CANNED.get(provider, []))}


def main() -> int:
    A.validate_cloud_key = fake_validate          # patch ที่ namespace ของ route (กัน network)
    # เคลียร์ test account ค้าง
    for a in list(account_store.all_public()):
        if a["label"].startswith("M16QA"):
            account_store.delete(a["id"])

    gem_id = ortr_id = gh_id = None
    try:
        # 1) add key → validate ดึง+persist
        r = A.add_api_key_account(A.ApiKeyAccountReq(provider="gemini", key="g-key", label="M16QA-gem"))
        gem_id = r["id"]
        check("add gemini → models_count=4 (persist)", r.get("models_count") == 4)
        check("account cache เก็บ 4 model", len(account_store.models_of(gem_id)) == 4)

        # 2) /models/available — chat only + overlay catalog + non-chat ถูกตัด
        opts = M.available(show_all=False)["options"]
        gem = {o["model"]: o for o in opts if o["provider"] == "gemini"}
        check("available: chat only (2) ไม่มี embed/video", set(gem) == {"gemini-2.5-flash", "gemini-3-flash"})
        check("available: curated overlay (2.5-flash จาก catalog)", gem["gemini-2.5-flash"]["curated"] is True)
        check("available: non-catalog chat แสดงด้วย (3-flash)", gem["gemini-3-flash"]["curated"] is False)

        # 3) /models/available?all=1 — non-chat โผล่แบบ selectable:false
        allo = {o["model"]: o for o in M.available(show_all=True)["options"] if o["provider"] == "gemini"}
        check("all=1: embed+video โผล่", {"text-embedding-004", "veo-2"} <= set(allo))
        check("all=1: non-chat selectable=false", allo["text-embedding-004"]["selectable"] is False
              and allo["veo-2"]["selectable"] is False)
        check("all=1: chat ยังเลือกได้", allo["gemini-2.5-flash"].get("selectable") is not False)

        # 4) OpenRouter — pricing จาก cache + routing
        r2 = A.add_api_key_account(A.ApiKeyAccountReq(provider="openrouter", key="or-key", label="M16QA-or"))
        ortr_id = r2["id"]
        check("openrouter: cloud_price จาก account cache", L.cloud_price("openrouter", "anthropic/claude-3.5-sonnet") == (3.0, 15.0))
        oropts = {o["model"]: o for o in M.available(show_all=False)["options"] if o["provider"] == "openrouter"}
        check("openrouter: chat only (flux image ถูกตัด)", set(oropts) == {"anthropic/claude-3.5-sonnet"})

        # 5) refresh — เพิ่ม model ใหม่ใน canned → diff added
        CANNED["gemini"].append(mi("gemini-4-pro", "chat", label="Gemini 4 Pro"))
        diff = A.refresh_models(gem_id)
        check("refresh: total=5", diff["total"] == 5)
        check("refresh: added=[gemini-4-pro]", diff["added"] == ["gemini-4-pro"])
        check("refresh: chat count=3", diff["chat"] == 3)

        # 6) GET /accounts/{id}/models — chat default / all
        check("account_models chat-only=3", A.account_models(gem_id, show_all=False)["total"] == 3)
        check("account_models all=5", A.account_models(gem_id, show_all=True)["total"] == 5)

        # 7) routing get_llm — provider เด้งไปทางที่ถูก + คงชื่อ model ที่ provider ต้องการ
        gllm = L.get_llm(LLMConfig(provider="gemini", model="gemini-2.5-flash", account_id=gem_id))
        check("routing gemini (litellm native)", "gemini-2.5-flash" in gllm.model)
        # OpenRouter: ต้องคง vendor sub-path 'anthropic/claude-3.5-sonnet' (กัน bug crewai ตัด prefix) + base_url
        orllm = L.get_llm(LLMConfig(provider="openrouter", model="anthropic/claude-3.5-sonnet", account_id=ortr_id))
        check("routing openrouter → คง vendor sub-path + base_url",
              orllm.model == "anthropic/claude-3.5-sonnet" and "openrouter.ai" in (orllm.base_url or ""))
        # GitHub Models: hosted_vllm passthrough → คง 'openai/gpt-4o' + base_url github
        r3 = A.add_api_key_account(A.ApiKeyAccountReq(provider="github", key="gh-key", label="M16QA-gh"))
        gh_id = r3["id"]
        ghllm = L.get_llm(LLMConfig(provider="github", model="openai/gpt-4o", account_id=gh_id))
        check("routing github → คง 'openai/gpt-4o' + base_url github",
              ghllm.model == "openai/gpt-4o" and "models.github.ai" in (ghllm.base_url or ""))
        gho = {o["model"]: o for o in M.available(show_all=False)["options"] if o["provider"] == "github"}
        check("github: chat only (embed ถูกตัด)", set(gho) == {"openai/gpt-4o"})

        # 8) backward-compat: catalog price ยังทำงาน, unknown → None
        check("compat: catalog price (claude opus)", L.cloud_price("claude", "claude-opus-4-8") == (5.0, 25.0))
        check("compat: unknown model → None", L.cloud_price("claude", "ghost") is None)
    finally:
        for aid in (gem_id, ortr_id, gh_id):
            if aid:
                account_store.delete(aid)

    print()
    if _FAILS:
        print(f"M16-9 QA: {len(_FAILS)} FAILED -> {_FAILS}")
        return 1
    print("M16-9 QA: ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
