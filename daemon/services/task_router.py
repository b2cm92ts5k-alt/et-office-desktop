"""TaskRouter — route user message → agent ที่เหมาะ → execution (M1-8, M6-9)

Flow (ตาม technical blueprint §04):
  1. keyword match หา agent
  2. broadcast task.routing
  3. ถ้าตั้ง workspace แล้ว (M6-6) → tool loop แบบ JSON action protocol (M6-9)
     ไม่งั้น → CrewAI Crew แชทธรรมดาแบบเดิม
  4. broadcast agent.status=working → Godot เล่นอนิเมชัน
  5. รันใน thread (sync) → broadcast task.completed
  6. broadcast agent.status=idle

ทำไม JSON protocol ไม่ใช่ native tool-calling: qwen3:8b เรียก function หลายขั้น
ผ่าน LiteLLM ไม่เสถียร (Risk register) — บังคับตอบ JSON ทีละ action แล้ว parse เอง
ตรงไปตรงมาและ debug ง่ายกว่า | task ซับซ้อนแนะนำสลับ agent เป็น cloud model (M4-6)
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timezone

from crewai import Agent, Crew, Process, Task

from ..adapters.llm_adapter import active_local_tag, context_budget, get_llm, ollama_chat
from ..models.schemas import AgentConfig, TaskLog
from .agent_registry import registry
from .cost_guard import cost_guard, est_tokens
from .log_service import log_service
from .memory_service import memory_service
from .mcp_service import mcp_service
from .permission_gate import permission_gate
from .settings_store import settings_store
from .tool_executor import (
    TOOLS_SPEC, WorkspaceError, execute, summarize, tool_allowed, workspace_root)
from .ws_manager import ws_manager

MAX_STEPS = 10          # action สูงสุดต่อ task — กัน loop ไม่รู้จบ
MAX_PARSE_FAILS = 2     # LLM ตอบไม่เป็น JSON กี่ครั้งถึงยอมรับเป็นคำตอบ text
MAX_TOOL_FAILS = 3      # tool ไม่รู้จัก/โดนบล็อคติดกันกี่ครั้งถึงยอมแพ้ attempt แล้ว retry
# retry schedule ต่อ task (M11-2, §3.2): attempt1 temp ปกติ → attempt2 temp=0 + เน้น schema
# ครบทุก attempt ยังพัง → circuit breaker: fail task + log (ไม่ retry อีก กัน agent วน loop กิน resource)
_TASK_ATTEMPTS = ((0.2, False), (0.0, True))  # (temperature, strict_nudge)


class _AttemptFailed(Exception):
    """attempt หนึ่งล้มเหลวแบบ retry ได้ (ชนเพดาน / tool พังซ้ำ) — ใช้ภายใน task_router"""

# schema หลวมสำหรับ tool-loop (M11-1, §3.1) — บังคับ output เป็น JSON object เสมอ (ตัด parse fail)
# ไม่ใช้ oneOf/required แยกสาขา (action vs final) เพราะ grammar ของ llama.cpp ซับซ้อนขึ้น
# model เล็กพลาดง่าย — ปล่อย field เป็น optional แล้วให้ logic เดิม (_extract_json) ตัดสินใจ
_ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "action": {
            "type": "object",
            "properties": {
                "tool": {"type": "string"},
                "args": {"type": "object"},
            },
            "required": ["tool", "args"],
        },
        "final": {"type": "string"},
    },
}

# M11-7 (§3.5) — reviewer ตอบ {ok, issues} บังคับ schema (reuse constrained JSON M11-1)
_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["ok", "issues"],
}
_REVIEWER_FALLBACK = (
    "คุณคือ Reviewer ตรวจ final ของ agent: ทำครบตามสั่งไหม / มี action จริงไหม / "
    "ภาษาตรงผู้ใช้ / ไม่มี error ค้าง. ตอบ JSON เท่านั้น {\"ok\": bool, \"issues\": [..]} "
    "งานคุยเฉย ๆ ที่ตอบครบ = ok=true")


def _reviewer_prompt() -> str:
    """system prompt ของ reviewer — อ่านจาก daemon/roles/reviewer.md (CEO แก้ได้), fallback inline"""
    try:
        from pathlib import Path
        text = (Path(__file__).parent.parent / "roles" / "reviewer.md").read_text(encoding="utf-8")
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) == 3:
                text = parts[2]
        return text.strip() or _REVIEWER_FALLBACK
    except Exception:
        return _REVIEWER_FALLBACK

_TOOL_LINES = "\n".join(
    f"- {name}({', '.join(spec['args'])}) — {spec['desc']}"
    for name, spec in TOOLS_SPEC.items())

_LOOP_PROMPT = """{system_prompt}

คุณทำงานอยู่ใน workspace: {root}
เครื่องมือที่ใช้ได้:
{tools}

ตอบเป็น JSON เท่านั้น เลือกรูปแบบใดรูปแบบหนึ่ง:
1. ทำ action ถัดไป (ทีละ 1 action):
{{"thought": "คิดสั้น ๆ", "action": {{"tool": "ชื่อ tool", "args": {{...}}}}}}
2. งานเสร็จแล้ว:
{{"final": "สรุปผลถึงผู้ใช้ ภาษาเดียวกับผู้ใช้"}}

กติกา:
- path ใช้แบบ relative ใต้ workspace เท่านั้น เช่น "docs/plan.md"
- ทุก action ต้องรอผู้ใช้อนุญาต — ถ้าโดนปฏิเสธ ให้ปรับแผนหรือสรุปเท่าที่ทำได้
- ห้ามตอบ final ว่า "ทำแล้ว" ถ้ายังไม่มี OBSERVATION ยืนยันว่า action สำเร็จจริง
- เฉพาะคำถามคุยเฉย ๆ ที่ไม่ต้องแตะไฟล์/รันคำสั่ง ถึงตอบ final ได้ทันที

ตัวอย่าง: ผู้ใช้สั่ง "สร้างไฟล์ a.txt เนื้อหา hi"
คุณ:   {{"thought": "ต้องเขียนไฟล์", "action": {{"tool": "write_file", "args": {{"path": "a.txt", "content": "hi"}}}}}}
ระบบ:  OBSERVATION: เขียนแล้ว: a.txt (2 ตัวอักษร)
คุณ:   {{"final": "สร้างไฟล์ a.txt เรียบร้อยแล้วครับ"}}"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_json(text: str) -> dict | None:
    """ดึง JSON object แรกจากคำตอบ LLM — ตัด <think> ของ qwen3 ก่อน"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    decoder = json.JSONDecoder()
    i = text.find("{")
    while i != -1:
        try:
            obj, _ = decoder.raw_decode(text[i:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        i = text.find("{", i + 1)
    return None


class TaskRouter:
    async def route_and_execute(self, message: str) -> TaskLog:
        """สร้าง task แล้วรันเบื้องหลัง — return ทันทีพร้อม task_id"""
        agent_cfg = self._match_agent(message)
        task = TaskLog(message=message, agent_id=agent_cfg.id, agent_name=agent_cfg.name)
        log_service.save_task(task)
        log_service.add("task", f"routing → {agent_cfg.name}: {message[:120]}", agent_cfg.id)

        await ws_manager.broadcast({
            "type": "task.routing",
            "data": {"task_id": task.task_id, "agent_id": agent_cfg.id,
                     "agent": agent_cfg.name, "message": message},
        })
        asyncio.create_task(self._execute(task, agent_cfg))
        return task

    def _match_agent(self, message: str) -> AgentConfig:
        """keyword match — agent ที่ keyword ตรงมากสุดชนะ, เสมอ/ไม่เจอ → ตัวแรก"""
        agents = registry.all()
        if not agents:
            raise RuntimeError("ไม่มี agent ใน registry")
        lower = message.lower()
        best, best_score = agents[0], 0
        for a in agents:
            score = sum(1 for kw in a.keywords if kw.lower() in lower)
            if score > best_score:
                best, best_score = a, score
        return best

    def _metrics(self, agent_cfg: AgentConfig, m: dict, started: float) -> dict:
        """ประกอบ field observability ต่อ hop (M11-5, §4.2) ใส่ใน WS event

        model/provider มาจาก ollama_chat (local) — ถ้า task พังก่อนเรียก LLM ใช้ค่าจาก cfg.
        tokens เป็น 0 สำหรับ cloud (CrewAI ยังไม่คาย usage — ไว้ทำรอบหน้า).
        """
        provider = m.get("provider") or agent_cfg.llm.provider
        model = m.get("model") or (
            active_local_tag() if agent_cfg.llm.provider == "ollama" else agent_cfg.llm.model)
        return {
            "model": model,
            "provider": provider,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "tokens_in": m.get("tokens_in", 0),
            "tokens_out": m.get("tokens_out", 0),
            "llm_calls": m.get("llm_calls", 0),
            "cache_hits": m.get("cache_hits", 0),
        }

    async def _execute(self, task: TaskLog, agent_cfg: AgentConfig) -> None:
        await self._set_status(agent_cfg.id, "working")
        task.status = "working"
        log_service.save_task(task)

        metrics: dict = {}
        started = time.monotonic()
        try:
            output = await asyncio.to_thread(self._run_agent, task, agent_cfg, metrics)
            task.status = "completed"
            task.output = output
            task.finished_at = _now()
            log_service.save_task(task)
            stat = self._metrics(agent_cfg, metrics, started)
            log_service.add("task",
                f"completed: {task.task_id} [{stat['model']} {stat['latency_ms']}ms "
                f"in{stat['tokens_in']}/out{stat['tokens_out']} cache{stat['cache_hits']}]",
                agent_cfg.id)
            # M11-11 — จด note งานนี้เข้า memory เฉพาะของ agent นี้ (ข้าม task ถัดไปจำได้)
            memory_service.add_agent_note(agent_cfg.id, f"{task.message[:80]} → {str(output)[:100]}")
            await ws_manager.broadcast({
                "type": "task.completed",
                "data": {"task_id": task.task_id, "agent_id": agent_cfg.id, "output": output, **stat},
            })
        except Exception as exc:  # LLM/network error — แจ้งทุก layer แล้ว agent กลับ idle
            task.status = "failed"
            task.output = str(exc)
            task.finished_at = _now()
            log_service.save_task(task)
            stat = self._metrics(agent_cfg, metrics, started)
            log_service.add("error", f"task {task.task_id} failed: {exc}", agent_cfg.id)
            await ws_manager.broadcast({
                "type": "task.failed",
                "data": {"task_id": task.task_id, "agent_id": agent_cfg.id, "error": str(exc), **stat},
            })
        finally:
            permission_gate.finish_task(task.task_id)  # ล้างสิทธิ์อนุมัติยกชุด (M6-8)
            await self._set_status(agent_cfg.id, "idle")

    def _run_agent(self, task: TaskLog, agent_cfg: AgentConfig, metrics: dict | None = None) -> str:
        """sync — เลือกเส้นทาง: workspace ตั้งแล้ว → tool loop (มี retry), ไม่งั้นแชทผ่าน Crew"""
        if str(settings_store.get("workspace_path") or "").strip():
            return self._run_tool_loop_retry(task, agent_cfg, metrics)
        return self._run_crew(task.message, agent_cfg)

    def _run_tool_loop_retry(self, task: TaskLog, agent_cfg: AgentConfig,
                             metrics: dict | None = None) -> str:
        """ห่อ tool loop ด้วย retry + circuit breaker (M11-2, §3.2)

        retry เมื่อ: exception (LLM/network), ชนเพดาน MAX_STEPS ไม่มี final, tool พังซ้ำ
        (ทั้งหมดโผล่เป็น exception จาก _run_tool_loop). user ปฏิเสธ action ไม่ใช่ failure.
        ครบทุก attempt → raise (circuit breaker) → _execute จับเป็น task.failed แจ้ง feed.
        """
        n = len(_TASK_ATTEMPTS)
        last = ""
        for i, (temp, strict) in enumerate(_TASK_ATTEMPTS, 1):
            try:
                out = self._run_tool_loop(task, agent_cfg, temperature=temp, strict=strict,
                                          metrics=metrics)
                if i > 1:
                    log_service.add("task", f"retry attempt {i}/{n} สำเร็จ: {task.task_id}", agent_cfg.id)
                return out
            except Exception as exc:  # _AttemptFailed รวมถึง LLM/network error — retry ได้
                last = str(exc)
                tail = "retry temp=0 + เน้น schema" if i < n else "circuit breaker — หยุด ไม่ retry อีก"
                log_service.add("error", f"attempt {i}/{n} ล้มเหลว: {last} → {tail}", agent_cfg.id)
        raise RuntimeError(f"ล้มเหลวหลัง retry {n} ครั้ง (circuit breaker): {last}")

    def _run_tool_loop(self, task: TaskLog, agent_cfg: AgentConfig,
                       *, temperature: float = 0.2, strict: bool = False,
                       metrics: dict | None = None) -> str:
        """JSON action protocol (M6-9) — LLM ตอบทีละ action ผ่าน permission gate เสมอ

        temperature/strict ส่งมาจาก retry wrapper (M11-2): รอบ retry ใช้ temp=0 + strict
        เพื่อบีบ output ให้นิ่งและตรง schema. raise _AttemptFailed เมื่อ attempt นี้ควร retry.
        """
        try:
            root = workspace_root()
        except WorkspaceError as exc:
            return f"ใช้ workspace ไม่ได้: {exc}"  # config พัง — retry ไม่ช่วย ส่งกลับเลย
        # local (ollama) → ยิง native /api/chat บังคับ JSON schema (M11-1); cloud → CrewAI LLM เดิม
        provider = agent_cfg.llm.provider
        # M11-10: cloud agent + เกิน budget → fallback local กันค่าบานปลาย + แจ้ง feed
        if provider != "ollama" and cost_guard.over_budget():
            log_service.add("error",
                f"💸 cost guard: เกิน budget cloud → {agent_cfg.name} ใช้ local ({active_local_tag()}) ชั่วคราว",
                agent_cfg.id)
            provider = "ollama"
        is_ollama = provider == "ollama"
        llm = None if is_ollama else get_llm(agent_cfg.llm, temperature=temperature)
        # M11-8: thinking agent (orchestrator/วางแผน) ปล่อยคิดก่อนตอบ → ปิด schema (think ขัดกับ format)
        # พึ่ง _extract_json + retry; worker (default) ใช้ schema + /no_think เร็ว+เป๊ะ
        thinking = bool(agent_cfg.thinking_mode)
        step_schema = None if thinking else _ACTION_SCHEMA
        # รวม MCP tools (M10-3) เข้ากับ tool ในตัว — ชื่อ namespaced mcp__<srv>__<tool>
        mcp_tools = mcp_service.tools()
        mcp_names = {t["name"] for t in mcp_tools}
        tool_lines = _TOOL_LINES
        if mcp_tools:
            tool_lines += "\n" + "\n".join(
                f"- {t['name']}({', '.join(t['args'])}) — {t['desc']}" for t in mcp_tools)
        system = _LOOP_PROMPT.format(
            system_prompt=agent_cfg.system_prompt or f"คุณคือ {agent_cfg.name} ({agent_cfg.role})",
            root=str(root), tools=tool_lines)
        if strict:  # รอบ retry (M11-2) — ย้ำกติกาให้ model เล็กตามให้แม่นขึ้น
            system += ("\n\n‼️ รอบแก้ตัว: ตอบ JSON ตามรูปแบบเป๊ะ ๆ เท่านั้น | "
                       "เลือก tool จากรายการข้างบนเท่านั้น | ใส่ args ให้ครบทุกตัว | "
                       "ทำ action ทีละขั้นจนเสร็จแล้วค่อยตอบ final")
        mem = memory_service.context_block(agent_cfg.id)  # M11-11 — team + per-agent memory
        if mem:
            system += "\n\n" + mem
        # context budget ตามขนาด model (M11-6) — เครื่องแรง = หน้าต่างกว้าง
        budget = context_budget(agent_cfg.llm.provider)
        if len(system) // 4 > budget["sys_budget_tok"]:  # ~4 ตัวอักษร/token (เตือนเฉย ๆ ไม่ตัด)
            log_service.add("info",
                f"⚠ system prompt ~{len(system)//4} tok เกินงบ {budget['sys_budget_tok']} (M11-6)",
                agent_cfg.id)

        def summarize_fn(chunk: list[dict], prior: str) -> str:
            """สรุป turn เก่าที่ตัดออกจาก window (M11-6) ด้วย model เดียวกับ agent"""
            convo = "\n".join(f"{m['role']}: {m['content']}" for m in chunk)
            msgs = [{"role": "system", "content":
                     "สรุปสั้น ๆ เป็น bullet ว่า agent ทำ action อะไรไปแล้วและผลเป็นยังไง "
                     "(เก็บชื่อไฟล์/คำสั่ง/ผลสำคัญ ตัดรายละเอียดยิบย่อย) ภาษาไทย /no_think"}]
            if prior:
                msgs.append({"role": "user", "content": "สรุปเดิม:\n" + prior})
            msgs.append({"role": "user", "content": "บทสนทนาที่ต้องสรุปเพิ่ม:\n" + convo})
            if is_ollama:
                return ollama_chat(msgs, temperature=0.3, stats=metrics, think=False)
            return str(llm.call(msgs))

        messages: list[dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": task.message},
        ]
        summary_state = {"summary": "", "covered": 0}
        parse_fails = 0
        actions_done = 0
        tool_fail_streak = 0
        final_pushback = False
        review_done = False
        for _step in range(MAX_STEPS):
            # ส่งเฉพาะ window (system + งานเดิม + สรุป + N turn ล่าสุด) — กัน context บวมจน quality ร่วง
            sent = self._compact_messages(messages, budget["keep_turns"], summary_state, summarize_fn)
            if is_ollama:
                raw = ollama_chat(sent, schema=step_schema, temperature=temperature,
                                  stats=metrics, think=thinking)
            else:
                raw = str(llm.call(sent))
                # cloud ไม่คาย usage → ประเมิน token เพื่อคิดค่า (M11-10) + เติม metrics (M11-5)
                t_in, t_out = est_tokens(sent), est_tokens([{"content": raw}])
                cost_guard.record(provider, t_in, t_out)
                if metrics is not None:
                    metrics["model"] = agent_cfg.llm.model
                    metrics["provider"] = provider
                    metrics["tokens_in"] = metrics.get("tokens_in", 0) + t_in
                    metrics["tokens_out"] = metrics.get("tokens_out", 0) + t_out
                    metrics["llm_calls"] = metrics.get("llm_calls", 0) + 1
            data = _extract_json(raw)

            if data is None:
                parse_fails += 1
                if parse_fails > MAX_PARSE_FAILS:
                    # ตอบ text ตลอด = model ตั้งใจคุยเฉย ๆ — ส่งเป็นคำตอบไปเลย
                    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user",
                                 "content": "ตอบเป็น JSON ตามรูปแบบที่กำหนดเท่านั้น"})
                continue

            if "final" in data:
                # กัน model เล็กอ้างว่า "ทำแล้ว" ทั้งที่ยังไม่มี action — ดันกลับ 1 ครั้ง
                # ถ้าเป็นแชทเฉย ๆ model จะยืนยัน final ซ้ำแล้วผ่านได้
                if actions_done == 0 and not final_pushback:
                    final_pushback = True
                    messages.append({"role": "assistant", "content": raw})
                    messages.append({"role": "user", "content":
                        "ยังไม่มี action ใดถูกทำเลย — ถ้างานนี้ต้องสร้าง/แก้ไฟล์หรือรันคำสั่ง "
                        "ให้ส่ง action ก่อน ถ้าเป็นคำถามคุยเฉย ๆ ให้ตอบ final เดิมซ้ำอีกครั้ง"})
                    continue
                final_text = str(data["final"])
                # reviewer รอบ 2 (M11-7) — same local model ตรวจ checklist; ติด → ตีกลับแก้ 1 ครั้ง
                if settings_store.get("reviewer_enabled") and not review_done:
                    review_done = True
                    verdict = self._review(task.message, final_text, is_ollama, llm, metrics)
                    if verdict and verdict.get("ok") is False:
                        issues = [str(x) for x in (verdict.get("issues") or [])]
                        log_service.add("task",
                            f"reviewer ตีกลับ {task.task_id}: {'; '.join(issues)[:200]}", agent_cfg.id)
                        messages.append({"role": "assistant", "content": raw})
                        messages.append({"role": "user", "content":
                            "Reviewer พบปัญหา ให้แก้แล้วส่ง final ใหม่:\n- " + "\n- ".join(issues)})
                        continue
                return final_text

            action = data.get("action") or {}
            tool = str(action.get("tool", ""))
            args = action.get("args") or {}
            is_mcp = tool in mcp_names
            if not tool_allowed(tool, agent_cfg.allowed_tools):
                # role นี้ไม่มีสิทธิ์ใช้ tool นี้ (M11-3) — บอก model ให้เลี่ยงไป tool ที่ใช้ได้
                tool_fail_streak += 1
                observation = (f"role '{agent_cfg.role}' ไม่มีสิทธิ์ใช้ tool '{tool}' — "
                               f"ใช้ได้เฉพาะ: {', '.join(agent_cfg.allowed_tools)}")
            elif tool not in TOOLS_SPEC and not is_mcp:
                tool_fail_streak += 1
                observation = f"ไม่รู้จัก tool '{tool}' — ที่มี: {', '.join(TOOLS_SPEC)}"
            else:
                summary = f"MCP เรียก {tool}" if is_mcp else summarize(tool, args)
                detail = json.dumps(args, ensure_ascii=False)[:2000]
                approved = permission_gate.request(
                    task.task_id, agent_cfg.id, agent_cfg.name, tool, summary, detail)
                if approved:
                    try:
                        observation = mcp_service.call(tool, args) if is_mcp else execute(tool, args)
                        actions_done += 1
                        tool_fail_streak = 0  # สำเร็จ → รีเซ็ต streak
                    except WorkspaceError as exc:
                        tool_fail_streak += 1
                        observation = f"โดนบล็อค: {exc}"
                else:
                    observation = "ผู้ใช้ปฏิเสธ action นี้ — ปรับแผน หรือสรุปงานเท่าที่ทำได้"

            # tool พัง/ไม่รู้จักติดกันหลายครั้ง = model หลง — ยอมแพ้ attempt นี้ให้ retry (M11-2)
            if tool_fail_streak >= MAX_TOOL_FAILS:
                raise _AttemptFailed(f"tool พัง/ไม่รู้จัก {tool_fail_streak} ครั้งติด")

            obs = observation
            if len(obs) > budget["obs_clip"]:  # ตัด observation ใหญ่ก่อนเข้า context (M11-6)
                obs = obs[:budget["obs_clip"]] + f"\n…(ตัดเพื่อประหยัด context, เต็ม {len(observation)} ตัวอักษร)"
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": f"OBSERVATION:\n{obs}"})

        # วน MAX_STEPS แล้วยังไม่ได้ final = งานไม่จบ → retry (รอบ retry temp=0 มักจบเร็วกว่า)
        raise _AttemptFailed(f"ชนเพดาน {MAX_STEPS} steps แล้วยังไม่มี final")

    def _review(self, task_msg: str, final_text: str, is_ollama: bool, llm, metrics: dict | None):
        """reviewer รอบ 2 (M11-7) — same local model ตรวจ final → คืน dict {ok, issues} หรือ None

        ใช้ active model เดิม (ไม่โหลด model เพิ่ม → ไม่ละเมิด 1-active-local). reviewer พัง
        ไม่ควรล้ม task → คืน None แล้วปล่อยผ่าน.
        """
        msgs = [
            {"role": "system", "content": _reviewer_prompt()},
            {"role": "user", "content":
                f"คำสั่งเดิมของผู้ใช้:\n{task_msg}\n\nคำตอบสุดท้ายของ agent:\n{final_text}\n\n"
                "ตรวจตาม checklist แล้วตอบ JSON {ok, issues}"},
        ]
        try:
            if is_ollama:
                raw = ollama_chat(msgs, schema=_REVIEW_SCHEMA, temperature=0.0, stats=metrics,
                                  think=False)
            else:
                raw = str(llm.call(msgs))
            return _extract_json(raw)
        except Exception:
            return None

    def _compact_messages(self, messages: list[dict], keep_turns: int,
                          summary_state: dict, summarize_fn) -> list[dict]:
        """sliding window + LLM summary (M11-6, §3.4)

        เก็บ system + งานเดิม (2 ตัวแรก) เต็มเสมอ; turn ท้ายสุด keep_turns ตัวเก็บเต็ม;
        turn เก่ากว่านั้นถูกสรุปครั้งเดียวแล้ว cache ใน summary_state (ไม่สรุปซ้ำทุก step).
        """
        head = messages[:2]
        tail = messages[2:]
        covered = summary_state["covered"]
        if len(tail) - covered > keep_turns:
            drop_to = len(tail) - keep_turns          # สรุปทุกอย่างก่อนหน้านี้ ยกเว้น keep_turns ท้าย
            chunk = tail[covered:drop_to]
            if chunk:
                summary_state["summary"] = summarize_fn(chunk, summary_state["summary"])
                summary_state["covered"] = drop_to
        kept = tail[summary_state["covered"]:]
        out = list(head)
        if summary_state["summary"]:
            out.append({"role": "user",
                        "content": "สรุปงานที่ทำไปแล้วก่อนหน้านี้ (ย่อ):\n" + summary_state["summary"]})
        out.extend(kept)
        return out

    def _run_crew(self, message: str, agent_cfg: AgentConfig) -> str:
        """sync — รันใน thread เพื่อไม่ block event loop"""
        backstory = agent_cfg.backstory or f"คุณคือ {agent_cfg.name} ทีมงาน ET Office"
        mem = memory_service.context_block(agent_cfg.id)  # M11-11 — team + per-agent memory
        if mem:
            backstory += "\n\n" + mem
        crew_agent = Agent(
            role=agent_cfg.role,
            goal=agent_cfg.system_prompt or f"ช่วยเหลือ user ในฐานะ {agent_cfg.role}",
            backstory=backstory,
            llm=get_llm(agent_cfg.llm),
            verbose=False,
        )
        crew_task = Task(
            description=message,
            agent=crew_agent,
            expected_output="คำตอบที่สมบูรณ์สำหรับคำขอของ user (ภาษาเดียวกับ user)",
        )
        crew = Crew(agents=[crew_agent], tasks=[crew_task],
                    process=Process.sequential, verbose=False)
        result = crew.kickoff()
        return getattr(result, "raw", str(result))

    async def _set_status(self, agent_id: str, status: str) -> None:
        registry.set_status(agent_id, status)
        await ws_manager.broadcast({
            "type": "agent.status",
            "data": {"agent_id": agent_id, "status": status},
        })


task_router = TaskRouter()
