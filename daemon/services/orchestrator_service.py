"""OrchestratorService (M15-5) — Sub-Agent: Producer แตกงาน → มอบหมาย → รวมผล

หลักการเดียวของ ET Office (CEO เคาะ 2026-06-20): คำสั่งทั่วไปของ CEO เข้า orchestrator เสมอ
1. **decompose** — Producer ยิง LLM (constrained JSON) แตกเป็น subtask + เลือก role ที่เหมาะ
   (งานง่าย = 1 subtask). decompose แนะนำ cloud (D1) แต่ทำ local ได้ fallback.
2. **dispatch** — แต่ละ subtask → match agent ตาม role → `task_router.run_sync()` (reuse tool-loop
   + permission gate เดิม 100%) ตามลำดับ. broadcast ทุกขั้น → Godot โชว์ agent ทำงานทีละตัว.
3. **synthesize** — รวมผลทุก subtask → Producer เรียบเรียงคำตอบสุดท้ายให้ CEO.

reuse สูงสุด: subtask = tool-loop เดิม (+skill M15-1). โค้ดใหม่ = แค่ loop decompose/dispatch/synthesize.
import task_router แบบ lazy กัน circular (task_router เรียก orchestrator ใน _execute).
"""
from __future__ import annotations

import json

from ..models.schemas import AgentConfig, TaskLog
from .agent_registry import registry
from .log_service import log_service
from .ws_manager import ws_manager

MAX_SUBTASKS = 5   # กันแตกเยอะเกินจน token/เวลาบาน

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "role": {"type": "string"},
                    "subtask": {"type": "string"},
                },
                "required": ["role", "subtask"],
            },
        }
    },
    "required": ["plan"],
}


def _workspace_files(limit: int = 40) -> list[str]:
    """ลิสต์ไฟล์ใน workspace (relative) ให้ subtask เห็นงานที่ทีมทำไว้ (M20-1 กันทำซ้ำ/หลงประเด็น)"""
    try:
        from .tool_executor import workspace_root
        root = workspace_root()
    except Exception:  # noqa: BLE001 — ไม่มี workspace → ไม่มี context ไฟล์
        return []
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and ".git" not in p.parts:
            out.append(p.relative_to(root).as_posix())
            if len(out) >= limit:
                break
    return out


def _subtask_context(goal: str, prior: list[str]) -> str:
    """บริบทให้ subtask (M20-1): เป้าหมายเดิมของ CEO + ไฟล์ที่มี + งานที่ทีมทำไปแล้ว
    → กัน output generic, ทำซ้ำ, ลืมโจทย์ (เช่นสั่ง mario แต่ได้เกมทั่วไป)"""
    parts = [f'เป้าหมายรวมที่ CEO สั่ง: "{goal}"  (งานย่อยของคุณต้องสอดคล้องกับเป้าหมายนี้)']
    files = _workspace_files()
    if files:
        parts.append("ไฟล์ในโปรเจกต์ตอนนี้ (อ่าน/ต่อยอดได้ — อย่าสร้างซ้ำของที่มีแล้ว):\n"
                     + "\n".join("- " + f for f in files))
    if prior:
        parts.append("ทีมทำมาแล้ว:\n" + "\n".join("- " + p for p in prior))
    return "\n\n".join(parts)


# M20-2 — ชนิดผลงานที่ subtask "ควรได้" → ใช้ verify กับ produced_kinds จาก tool-loop
# ดู role ของ agent เป็นหลัก (แม่นกว่าเดาจากข้อความ subtask ที่ LLM เขียนหลากหลาย เช่น
# "สร้างสเก็ตช์/โมเดล 3D" ที่ไม่ match "วาด") — Artist=ต้องได้ภาพเสมอ, Sound=เสียง, Dev=code
def _expected_kind(agent, subtask: str) -> str | None:
    role = (getattr(agent, "role", "") + " " + " ".join(getattr(agent, "keywords", []) or [])).lower()
    if any(k in role for k in ("artist", "animator", "ศิลป", "วาด", "กราฟิก", "illustrat", "pixel", "ภาพ")):
        return "image"
    if any(k in role for k in ("sound", "audio", "เสียง", "music", "ดนตรี", "composer")):
        return "audio"
    if any(k in role for k in ("developer", "coder", "programmer", "engineer", "โปรแกรม", "วิศวกร", "เขียนโค้ด")):
        return "code"
    s = subtask.lower()   # fallback: ข้อความ subtask ระบุชนิดชัด (เผื่อ role กว้าง)
    if any(k in s for k in ("เสียง", "sound", ".wav", "เพลง")):
        return "audio"
    if any(k in s for k in ("วาดรูป", "สร้างภาพ", "สเก็ตช์", "sketch", ".png", "sprite", "artwork")):
        return "image"
    if any(k in s for k in (".cs", ".py", ".gd", "เขียนโค้ด", "script", "สคริปต์")):
        return "code"
    return None   # design/research/test/doc → ไม่บังคับชนิด


def _expects_file(subtask: str) -> bool:
    """เดาว่า subtask นี้ควรผลิตไฟล์งานจริงไหม (M19-2 verify) — เจาะจงพอไม่ให้ false positive
    กับงานวิเคราะห์/คุยล้วน. ใช้คู่กับ produced_output flag จาก tool-loop"""
    s = subtask.lower()
    kws = ("เขียนไฟล์", "สร้างไฟล์", "เขียนโค้ด", "เขียนเอกสาร", "สร้างเอกสาร", "บันทึกไฟล์",
           "code", "script", "สคริปต์", ".py", ".md", ".cs", ".gd", "gdd", "main.py", "เกม")
    return any(k in s for k in kws)


def _parse_plan(raw: str) -> list[dict]:
    """ดึง plan จากคำตอบ LLM แบบทนทาน (fix 2026-06-21) — รองรับหลายรูปแบบที่ model มักตอบ:
    {"plan":[...]}, array เปล่า [...], หรือ object เดี่ยว {"role","subtask"} → คืน [{role,subtask}]
    """
    import re

    from .task_router import _extract_json
    txt = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL)
    steps = None
    obj = _extract_json(txt)
    if isinstance(obj, dict) and isinstance(obj.get("plan"), list):
        steps = obj["plan"]                  # {"plan":[...]} — รูปแบบหลัก
    if steps is None:                        # array ดิบ [...] (ต้องเช็กก่อน single กัน _extract_json คว้า element แรก)
        i = txt.find("[")
        while i != -1 and steps is None:
            try:
                arr, _ = json.JSONDecoder().raw_decode(txt[i:])
                if isinstance(arr, list):
                    steps = arr
            except json.JSONDecodeError:
                pass
            i = txt.find("[", i + 1)
    if steps is None and isinstance(obj, dict) and obj.get("subtask"):
        steps = [obj]                        # object เดี่ยว = งาน 1 ขั้น
    if not isinstance(steps, list):
        return []
    out = []
    for s in steps[:MAX_SUBTASKS]:
        if isinstance(s, dict) and s.get("subtask"):
            out.append({"role": str(s.get("role", "")), "subtask": str(s["subtask"])})
    return out


class OrchestratorService:
    def _team(self) -> list[AgentConfig]:
        """ทีมที่มอบงานได้ — ทุก agent ยกเว้น CEO (CEO ไม่ลงมือเอง M13-8)"""
        return [a for a in registry.all() if not a.is_ceo]

    def _pick_agent(self, role: str, subtask: str) -> AgentConfig | None:
        """หา agent ที่ role/keyword ตรงกับที่ plan ระบุ — ไม่เจอ → keyword match จาก subtask"""
        team = self._team()
        if not team:
            return None
        rl = (role or "").lower().strip()
        if rl:
            for a in team:
                if rl in a.role.lower() or rl in a.name.lower() or any(rl in k.lower() for k in a.keywords):
                    return a
        from .task_router import task_router
        picked = task_router._match_agent(subtask)
        return picked if not picked.is_ceo else (team[0] if team else None)

    def _decompose(self, message: str, producer: AgentConfig, metrics: dict) -> list[dict]:
        """แตกงานเป็น plan [{role, subtask}] — งานง่าย = 1 subtask. คืน [] ถ้าแตกไม่ได้

        ทนทาน (fix 2026-06-21): cloud ลอง 2 ครั้ง + parse ยืดหยุ่น (รองรับ array/object เดี่ยว);
        cloud ล้ม/ว่าง (เช่น 429 free tier) → fallback แตกงานด้วย local ollama (schema บังคับ)
        เพื่อให้ "การแจกงาน" ยังเกิดแม้ cloud model ของ Producer มีปัญหา.
        """
        roles = ", ".join(sorted({f"{a.role}" for a in self._team()})) or "ทั่วไป"
        sys = (
            "คุณคือหัวหน้าทีม (Producer) แตกคำสั่งของ CEO เป็นงานย่อยให้ลูกทีมทำ.\n"
            f"ลูกทีมที่มี (role): {roles}\n"
            f"กติกา: แตกเป็นงานย่อยที่ทำได้จริงไม่เกิน {MAX_SUBTASKS} ข้อ, เรียงตามลำดับการทำ, "
            "แต่ละข้อระบุ role ลูกทีมที่เหมาะ (เลือกจากรายการข้างบน) และคำสั่งย่อยที่ชัดเจน. "
            "งานง่ายแตกแค่ 1 ข้อก็ได้.\n"
            'ตอบเป็น JSON object เดียวรูปแบบนี้เท่านั้น: {"plan":[{"role":"...","subtask":"..."}]} '
            "ห้ามมีข้อความทักทาย/อธิบาย/markdown อื่นนอก JSON."
        )
        messages = [{"role": "system", "content": sys}, {"role": "user", "content": message}]
        from ..adapters.llm_adapter import get_llm, ollama_chat
        from .cost_guard import cost_guard

        use_local = producer.llm.provider == "ollama" or cost_guard.over_budget()
        if not use_local:  # cloud — ลอง 2 ครั้ง, parse ยืดหยุ่น
            try:
                llm = get_llm(producer.llm, temperature=0.3)
                for _ in range(2):
                    plan = _parse_plan(str(llm.call(messages)))
                    if plan:
                        return plan
            except Exception as exc:  # noqa: BLE001 — cloud ล้ม (429/เน็ต) → ลอง local ต่อ
                log_service.add("error", f"decompose cloud ล้ม ({str(exc)[:80]}) → แตกงานด้วย local แทน", producer.id)
            use_local = True
        if use_local:  # local ollama — schema บังคับ JSON (เสถียรกว่า + ฟรี ไม่ติดโควต้า)
            try:
                raw = ollama_chat(messages, schema=PLAN_SCHEMA, temperature=0.3, stats=metrics, think=False)
                return _parse_plan(raw)
            except Exception as exc:  # noqa: BLE001
                log_service.add("error", f"decompose local ล้มเหลว: {str(exc)[:120]}", producer.id)
        return []

    def _synthesize(self, message: str, results: list[tuple], producer: AgentConfig, metrics: dict) -> str:
        """รวมผล subtask → คำตอบสุดท้ายให้ CEO (M19-2: header สถานะคำนวณจากโค้ด ไม่ให้ LLM หลอกว่าเสร็จ)"""
        done = sum(1 for *_, st in results if st == "done")
        bad = [r for r in results if r[3] != "done"]
        # header ความจริง — ไม่พึ่ง LLM (กัน Producer สรุปว่า "เสร็จ" ทั้งที่มีขั้นล้ม/ข้าม)
        icons = {"done": "✅", "failed": "❌", "skipped": "⏭️", "incomplete": "⚠️"}
        header = ""
        if bad:
            header = f"⚠️ งานยังไม่ครบ — สำเร็จ {done}/{len(results)} ขั้น\n" + "\n".join(
                f"{icons.get(st, '•')} {a.name}: {str(sub)[:60]}" for a, sub, _o, st in results) + "\n\n"
        if len(results) == 1 and not bad:
            return results[0][2]   # งานเดี่ยวสำเร็จ — ไม่ต้องเรียบเรียงซ้ำ
        body = "\n\n".join(f"[{a.name} ({a.role}) · {st}] {sub}\n→ {out}" for a, sub, out, st in results)
        rule = ("ถ้ามีขั้นที่ ❌/⏭️/⚠️ ห้ามบอกว่า 'เสร็จสมบูรณ์' — บอกตามจริงว่าได้อะไร ขาด/ติดอะไร "
                if bad else "")
        sys = ("คุณคือ Producer สรุปผลงานลูกทีมให้ CEO กระชับ เป็นระเบียบ บอกว่าได้อะไร/เหลืออะไร. "
               + rule + "ภาษาไทย /no_think")
        messages = [{"role": "system", "content": sys},
                    {"role": "user", "content": f"คำสั่งเดิม: {message}\n\nผลงานลูกทีม:\n{body}"}]
        from ..adapters.llm_adapter import get_llm, ollama_chat
        from .cost_guard import cost_guard
        try:
            if producer.llm.provider == "ollama" or cost_guard.over_budget():
                summary = ollama_chat(messages, temperature=0.4, stats=metrics, think=False)
            else:
                summary = str(get_llm(producer.llm, temperature=0.4).call(messages))
        except Exception:  # noqa: BLE001 — สรุปไม่ได้ → ส่งผลดิบรวมกัน
            summary = body
        return header + summary   # header (ความจริง) นำหน้าเสมอเมื่อมีขั้นไม่สำเร็จ

    def run(self, task: TaskLog, producer: AgentConfig, metrics: dict, loop) -> str:
        """แตกงาน → มอบหมาย → รวมผล (sync, เรียกจาก _execute ผ่าน to_thread)"""
        def emit(etype: str, data: dict) -> None:
            ws_manager.broadcast_threadsafe(loop, {"type": etype, "data": {"task_id": task.task_id, **data}})

        from .task_router import task_router
        from .permission_gate import permission_gate

        plan = self._decompose(task.message, producer, metrics)
        if not plan:   # decompose ล้ม → ทำงานเดี่ยวด้วย agent ที่ match (กันค้าง)
            agent = self._pick_agent("", task.message) or producer
            log_service.add("task", f"orchestrate: แตกงานไม่ได้ → ทำเดี่ยวโดย {agent.name}", producer.id)
            return task_router.run_sync(
                TaskLog(message=task.message, agent_id=agent.id, agent_name=agent.name), agent, metrics)

        log_service.add("task", f"orchestrate: {producer.name} แตกเป็น {len(plan)} งาน", producer.id)
        emit("orchestrate.plan", {"steps": [{"role": s["role"], "subtask": s["subtask"]} for s in plan]})

        from .task_router import _Rejected
        results: list[tuple] = []
        prior: list[str] = []   # M20-1 — สรุปงานที่ทีมทำไปแล้ว ส่งเป็น context ให้ขั้นถัดไป
        stopped = False   # M19-1 — มีขั้นถูก REJECT → ข้ามขั้นที่เหลือ (มักพึ่งกันตามลำดับ)
        for i, step in enumerate(plan, 1):
            agent = self._pick_agent(step["role"], step["subtask"])
            if agent is None:
                continue
            if stopped:   # ขั้นก่อนหน้าถูกปฏิเสธ → ไม่ทำต่อ (กัน Tester เทสของที่ไม่มี)
                results.append((agent, step["subtask"], "⏭️ ข้าม — ขั้นก่อนหน้าถูกปฏิเสธ", "skipped"))
                log_service.add("task", f"  {i}/{len(plan)} ข้าม {agent.name} (ขั้นก่อนถูกปฏิเสธ)", agent.id)
                continue
            emit("orchestrate.subtask", {"index": i, "total": len(plan),
                                         "agent_id": agent.id, "agent": agent.name, "subtask": step["subtask"]})
            # agent.status → Godot/sidebar reuse handler เดิม: sub-agent สว่าง/ทำงานทีละตัว (M15-7)
            emit("agent.status", {"agent_id": agent.id, "status": "working"})
            log_service.add("task", f"  {i}/{len(plan)} → {agent.name}: {step['subtask'][:80]}", agent.id)
            # M20-1 — แนบ context (เป้าหมายเดิม + ไฟล์ที่มี + งานคนก่อน) ให้ subtask ไม่ generic/ทำซ้ำ
            sub_msg = _subtask_context(task.message, prior) + "\n\nงานย่อยของคุณ: " + step["subtask"]
            sub = TaskLog(message=sub_msg, agent_id=agent.id, agent_name=agent.name)
            sub_m: dict = {}
            status = "done"
            try:
                out = task_router.run_sync(sub, agent, sub_m)
                # M20-2 verify ตามชนิดงาน (ดู role) — Artist ต้องได้ไฟล์ภาพ, Sound เสียง, Dev code
                exp = _expected_kind(agent, step["subtask"])
                kinds = set(sub_m.get("produced_kinds") or [])
                if exp and exp not in kinds:
                    status = "incomplete"
                    out = f"⚠️ ควรได้ไฟล์ '{exp}' แต่ไม่มี (ได้: {', '.join(sorted(kinds)) or 'ไม่มีไฟล์'}):\n{out}"
                # M19-2 verify — งานที่ควรสร้างไฟล์ แต่ไม่มี output จริง → ไม่ครบ (กันหลอกเสร็จ)
                elif sub_m.get("produced_output") is False and _expects_file(step["subtask"]):
                    status = "incomplete"
                    out = f"⚠️ อ้างว่าเสร็จแต่ไม่มีไฟล์งานเกิดขึ้นจริง:\n{out}"
            except _Rejected:
                out = "❌ ถูกปฏิเสธโดยผู้ใช้"
                status = "failed"
                stopped = True
                log_service.add("error", f"subtask {i} โดย {agent.name} ถูกปฏิเสธ → หยุดขั้นที่เหลือ", agent.id)
            except Exception as exc:  # noqa: BLE001 — subtask พัง → จดแล้วไปต่อ (อาจเป็นงานอิสระ)
                out = f"❌ ทำไม่สำเร็จ: {str(exc)[:100]}"
                status = "failed"
                log_service.add("error", f"subtask {i} โดย {agent.name} ล้มเหลว: {str(exc)[:100]}", agent.id)
            finally:
                permission_gate.finish_task(sub.task_id)
                for k in ("tokens_in", "tokens_out", "llm_calls", "cache_hits"):  # รวม token เข้างานหลัก
                    if sub_m.get(k):
                        metrics[k] = metrics.get(k, 0) + sub_m[k]
            results.append((agent, step["subtask"], out, status))
            prior.append(f"{agent.name} ({status}): {step['subtask'][:50]} → {str(out)[:80]}")  # M20-1
            emit("agent.status", {"agent_id": agent.id, "status": "idle"})
            emit("orchestrate.subtask.done", {"index": i, "agent_id": agent.id, "status": status})

        return self._synthesize(task.message, results, producer, metrics)


orchestrator_service = OrchestratorService()
