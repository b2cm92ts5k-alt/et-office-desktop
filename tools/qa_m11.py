"""QA Gate M11 — Multi-Agent Tuning (M11-1..M11-11)

รันแบบ import ตรง (ไม่ต้องมี daemon): python tools/qa_m11.py
ครอบคลุม: constrained JSON, retry/circuit breaker, tool whitelist, cache, observability,
context discipline, reviewer, think/no_think, specialist cloud, cost guard, per-agent memory
+ ยืนยันกฎ 1-active-local (M7-8) ไม่ถูกฝ่า

live ollama เป็น optional: ถ้า server ไม่ตอบจะ skip (ไม่ทำ gate fail) — โครงสร้าง/logic ตรวจครบเสมอ
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root → import daemon

_results: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, info: str = "") -> None:
    _results.append((bool(ok), name, info))
    print(("PASS" if ok else "FAIL"), "-", name, (f"  [{info}]" if info else ""))


def main() -> None:
    from daemon.adapters import llm_adapter as LA
    from daemon.services import task_router as TR
    from daemon.services import tool_executor as TE
    from daemon.services.settings_store import settings_store, DEFAULTS
    from daemon.models.schemas import AgentConfig, AgentUpdate

    # ---------- M11-1 Constrained JSON ----------
    print("--- M11-1 Constrained JSON ---")
    check("ollama_chat มีใน adapter", hasattr(LA, "ollama_chat"))
    sk = TR._ACTION_SCHEMA.get("properties", {})
    check("action schema มี thought/action/final", all(k in sk for k in ("thought", "action", "final")))

    # ---------- M11-2 Retry + circuit breaker ----------
    print("\n--- M11-2 Retry + circuit breaker ---")
    check("_TASK_ATTEMPTS = (temp0.2,F)+(temp0,strict)", TR._TASK_ATTEMPTS == ((0.2, False), (0.0, True)))
    check("MAX_TOOL_FAILS == 3", TR.MAX_TOOL_FAILS == 3)
    check("มี _AttemptFailed", hasattr(TR, "_AttemptFailed"))
    R = TR.TaskRouter()
    TR.log_service.add = lambda *a, **k: None  # ปิด log ระหว่างเทส

    class _T:  # fake task/agent
        task_id = "qa"; message = "hi"
    class _A:
        id = "qa"; name = "C"

    calls = []
    def loop_ok(self, t, a, **k):
        calls.append((k.get("temperature"), k.get("strict")))
        b = next(_b)
        if isinstance(b, Exception):
            raise b
        return b
    _b = iter([TR._AttemptFailed("ceiling"), "RECOVERED"])
    TR.TaskRouter._run_tool_loop = loop_ok
    out = R._run_tool_loop_retry(_T(), _A())
    check("retry: attempt1 พัง→attempt2 สำเร็จ", out == "RECOVERED" and calls == [(0.2, False), (0.0, True)])
    _b = iter([TR._AttemptFailed("a"), RuntimeError("b")])
    calls.clear()
    try:
        R._run_tool_loop_retry(_T(), _A())
        check("circuit breaker raise", False)
    except RuntimeError as e:
        check("circuit breaker หลังครบ attempt", "circuit breaker" in str(e) and len(calls) == 2)

    # ---------- M11-3 Tool whitelist ----------
    print("\n--- M11-3 Tool whitelist ---")
    check("AgentConfig.allowed_tools มี", "allowed_tools" in AgentConfig.model_fields)
    check("tool_allowed ว่าง=อนุญาตทุก tool", TE.tool_allowed("git_push", []) and TE.tool_allowed("x", None))
    check("tool_allowed whitelist บล็อก", not TE.tool_allowed("git_push", ["read_file"]))
    check("designer preset ไม่มี git_push", "git_push" not in TE.ROLE_TOOL_PRESETS["designer"])
    check("coder preset มี git_push", "git_push" in TE.ROLE_TOOL_PRESETS["coder"])

    # ---------- M11-4 Cache ----------
    print("\n--- M11-4 Cache layer ---")
    check("CACHE_TEMP_MAX == 0.5", LA.CACHE_TEMP_MAX == 0.5)
    LA.cache_clear()
    for i in range(LA.CACHE_MAX + 5):
        LA._cache_put(f"k{i}", f"v{i}")
    check("LRU evict ที่ CACHE_MAX", len(LA._cache) == LA.CACHE_MAX and LA._cache_get("k0") is None)
    k1 = LA._cache_key("m", [{"c": 1}], 0.2, None)
    k2 = LA._cache_key("m", [{"c": 1}], 0.0, None)
    check("cache key ไวต่อ temperature", k1 != k2)

    # ---------- M11-5 Observability ----------
    print("\n--- M11-5 Observability ---")
    cfg = AgentConfig(name="C", role="coder")
    st = R._metrics(cfg, {"model": "qwen3:8b", "provider": "ollama", "tokens_in": 10,
                          "tokens_out": 5, "llm_calls": 1, "cache_hits": 2}, __import__("time").monotonic())
    check("_metrics ครบ field", all(k in st for k in
          ("model", "provider", "latency_ms", "tokens_in", "tokens_out", "cache_hits")))
    import inspect
    check("ollama_chat รับ stats", "stats" in inspect.signature(LA.ollama_chat).parameters)

    # ---------- M11-6 Context discipline ----------
    print("\n--- M11-6 Context discipline ---")
    cb = LA.context_budget("claude")
    check("context_budget cloud กว้าง", cb["keep_turns"] == 20)
    for tag, exp in [("qwen3:1.7b", 6), ("qwen3:8b", 8), ("qwen3:14b", 12), ("qwen3:32b", 16)]:
        check(f"preset {tag} keep={exp}", LA.CONTEXT_PRESETS[tag]["keep_turns"] == exp)
    ss = {"summary": "", "covered": 0}
    msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "u"}]
    for i in range(10):
        msgs.append({"role": "assistant" if i % 2 == 0 else "user", "content": f"t{i}"})
    nsum = []
    sent = R._compact_messages(msgs, 4, ss, lambda chunk, prior: nsum.append(1) or "SUM")
    check("compact: window + สรุป overflow ครั้งเดียว", len(nsum) == 1 and ss["covered"] == 6
          and sent[2]["content"].startswith("สรุปงาน"))

    # ---------- M11-7 Reviewer ----------
    print("\n--- M11-7 Reviewer ---")
    check("DEFAULTS มี reviewer_enabled", "reviewer_enabled" in DEFAULTS and DEFAULTS["reviewer_enabled"] is False)
    check("_REVIEW_SCHEMA required ok+issues", set(TR._REVIEW_SCHEMA["required"]) == {"ok", "issues"})
    check("roles/reviewer.md มีจริง", (Path(__file__).resolve().parent.parent /
          "daemon" / "roles" / "reviewer.md").exists())
    rp = TR._reviewer_prompt()
    check("reviewer prompt โหลด+ตัด frontmatter", "ok" in rp and not rp.startswith("---"))

    # ---------- M11-8 think/no_think ----------
    print("\n--- M11-8 think/no_think ---")
    check("AgentConfig.thinking_mode default False", AgentConfig(name="x", role="y").thinking_mode is False)
    check("ollama_chat รับ think", "think" in inspect.signature(LA.ollama_chat).parameters)
    check("AgentUpdate มี thinking_mode", "thinking_mode" in AgentUpdate.model_fields)

    # ---------- M11-9 Specialist cloud ----------
    print("\n--- M11-9 Specialist cloud ---")
    check("specialist producer→claude", (LA.specialist_for("producer") or {}).get("provider") == "claude")
    check("specialist designer→openai", (LA.specialist_for("นักออกแบบ design") or {}).get("provider") == "openai")
    check("specialist researcher→gemini", (LA.specialist_for("research วิจัย") or {}).get("provider") == "gemini")
    check("specialist no-match→None", LA.specialist_for("พ่อครัว") is None)
    check("available_cloud_providers ครบ 3", set(LA.available_cloud_providers()) == {"claude", "gemini", "openai"})

    # ---------- M11-10 Cost guard ----------
    print("\n--- M11-10 Cost guard ---")
    from daemon.services.cost_guard import CostGuard, est_tokens
    check("DEFAULTS มี cost keys", all(k in DEFAULTS for k in
          ("cost_guard_enabled", "cost_daily_usd", "cost_hourly_usd")))
    check("est_tokens ~chars/4", est_tokens([{"content": "x" * 400}]) == 100)
    cg = CostGuard()
    check("local cost = 0", cg.record("ollama", "qwen3:8b", 1000, 1000) == 0.0)
    # opus 4.8 = $5 in + $25 out ต่อ 1M → 1M+1M = $30
    usd = cg.record("claude", "claude-opus-4-8", 1_000_000, 1_000_000)
    check("per-model price (opus 1M+1M = $30)", abs(usd - 30.0) < 1e-6)
    old_e, old_d = settings_store.get("cost_guard_enabled"), settings_store.get("cost_daily_usd")
    settings_store._values["cost_guard_enabled"] = True
    settings_store._values["cost_daily_usd"] = 5.0
    settings_store._values["cost_hourly_usd"] = 0.0
    check("over_budget เมื่อ $30 > cap $5", cg.over_budget() is True)
    settings_store._values["cost_guard_enabled"] = False
    check("ปิด guard → ไม่ over", cg.over_budget() is False)
    settings_store._values["cost_guard_enabled"] = old_e
    settings_store._values["cost_daily_usd"] = old_d

    # ---------- M11-13 Cloud model catalog ----------
    print("\n--- M11-13 Cloud model catalog ---")
    check("gemini catalog = free tier", len(LA.cloud_models("gemini")) >= 3
          and all(m["tier"] == "free" for m in LA.cloud_models("gemini")))
    check("claude/openai = paid", all(m["tier"] == "paid" for m in LA.cloud_models("claude"))
          and len(LA.cloud_models("openai")) >= 5)
    check("cloud_price opus = (5,25)", LA.cloud_price("claude", "claude-opus-4-8") == (5.0, 25.0))
    check("cloud_price gemini free = (0,0)", LA.cloud_price("gemini", "gemini-2.5-flash") == (0.0, 0.0))
    check("cloud_price unknown → None", LA.cloud_price("openai", "ไม่มีจริง") is None)

    # ---------- M11-11 Per-agent memory ----------
    print("\n--- M11-11 Per-agent memory ---")
    import daemon.services.memory_service as MS
    MS.MEMORY_PATH = Path(tempfile.mkdtemp()) / "mem.json"
    M = MS.MemoryService()
    M.set_team("sprint: ทำ M11")
    M.add_agent_note("coder", "แก้ bug login")
    M.add_agent_note("designer", "ทำไอคอน")
    cbc, cbd = M.context_block("coder"), M.context_block("designer")
    check("memory scoped: coder ไม่เห็นงาน designer", "bug login" in cbc and "ไอคอน" not in cbc)
    check("team memory แชร์ทั้งคู่", "sprint" in cbc and "sprint" in cbd)
    for i in range(20):
        M.add_agent_note("coder", f"n{i}")
    check("notes cap ที่ NOTES_PER_AGENT", len(M.agent_notes("coder")) == MS.NOTES_PER_AGENT)
    M.clear_agent("coder")
    check("clear_agent scoped", M.agent_notes("coder") == [] and M.agent_notes("designer"))

    # ---------- กฎเหล็ก M7-8: 1 active local ----------
    print("\n--- invariant: 1-active-local (M7-8) ยังอยู่ ---")
    src = Path(LA.__file__).read_text(encoding="utf-8")
    check("get_llm ollama coerce active_local_tag", "active_local_tag()" in src and
          'f"ollama/{active_local_tag()}"' in src)
    check("ollama_chat ใช้ active_local_tag", "model = active_local_tag()" in src)

    # ---------- route wiring (ต้อง import app) ----------
    print("\n--- route wiring (M11-7/9/10/11) ---")
    try:
        import daemon.main
        paths = {getattr(r, "path", "") for r in daemon.main.app.routes}
        for p in ("/settings/reviewer", "/settings/specialist", "/settings/cost", "/settings/team-memory"):
            check(f"route {p}", p in paths)
    except Exception as e:  # noqa: BLE001
        check("import daemon.main (route check)", False, str(e)[:60])

    # ---------- live ollama (optional) ----------
    print("\n--- live ollama (optional, skip ถ้า server ไม่ตอบ) ---")
    if LA.ollama_ok():
        try:
            LA.cache_clear()
            msgs = [{"role": "user", "content": "ตอบ JSON เท่านั้น"}]
            import json as _j
            raw = LA.ollama_chat(msgs, schema=TR._ACTION_SCHEMA, temperature=0.0)
            _j.loads(raw)
            check("live: schema บังคับ JSON parse ได้", True)
        except Exception as e:  # noqa: BLE001
            check("live: schema บังคับ JSON parse ได้", False, str(e)[:60])
    else:
        print("SKIP - ollama server ไม่ตอบ (โครงสร้าง/logic ตรวจครบแล้ว)")

    passed = sum(1 for ok, _, _ in _results if ok)
    total = len(_results)
    print(f"\n=== M11 QA: {passed}/{total} PASS ===")
    if passed != total:
        print("FAILED:", [n for ok, n, _ in _results if not ok])
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
