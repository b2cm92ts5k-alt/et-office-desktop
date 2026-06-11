"""SocialService — agent ว่างจับคู่คุยกัน → อาจกลายเป็น proposal (M3-9)

Loop ตาม technical blueprint §social:
  ทุก social_interval_sec → ถ้ามี agent idle ≥2 และสุ่มผ่าน social_chance
  → จับคู่ → ตั้ง collab (Godot พาเดินไป meeting) → CrewAI คุยกัน 2 task
  → ถ้าจบด้วย "PROPOSAL:" → สร้าง proposal (เคารพ cooldown — ไม่ spam)
ปรับจูน runtime ได้ผ่าน PUT /settings/social โดยไม่ต้อง restart
"""
from __future__ import annotations

import asyncio
import random

from crewai import Agent, Crew, Process, Task

from ..adapters.llm_adapter import get_llm
from ..models.schemas import AgentConfig
from .agent_registry import registry
from .log_service import log_service
from .proposal_service import proposal_service
from .settings_store import settings_store
from .ws_manager import ws_manager

PROPOSAL_MARKER = "PROPOSAL:"
CHAT_SNIPPET_CHARS = 120   # ความยาวข้อความที่ส่งให้ Godot โชว์ bubble


class SocialService:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._chatting = False

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(float(settings_store.get("social_interval_sec")))
            try:
                await self._tick()
            except Exception as exc:  # social พังต้องไม่ล้ม daemon
                log_service.add("error", f"social loop: {exc}")

    async def _tick(self) -> None:
        if not settings_store.get("social_enabled") or self._chatting:
            return
        # cooldown: เพิ่งมี proposal ไป → ข้ามรอบ กัน spam (QA gate M3-12)
        since = proposal_service.seconds_since_last()
        cooldown = float(settings_store.get("proposal_cooldown_sec"))
        if since is not None and since < cooldown:
            return
        idle = [a for a in registry.all() if a.status == "idle"]
        if len(idle) < 2 or random.random() >= float(settings_store.get("social_chance")):
            return
        pair = random.sample(idle, 2)
        self._chatting = True
        try:
            await self._run_chat(pair[0], pair[1])
        finally:
            self._chatting = False

    async def _run_chat(self, a: AgentConfig, b: AgentConfig) -> None:
        log_service.add("social", f"{a.name} ชวน {b.name} คุยเล่น", a.id)
        await ws_manager.broadcast({
            "type": "social.meetup",
            "data": {"agents": [a.id, b.id], "names": [a.name, b.name]},
        })
        for agent in (a, b):
            await self._set_status(agent.id, "collab")

        try:
            text = await asyncio.to_thread(self._run_crew, a, b)
        except Exception as exc:
            log_service.add("error", f"social chat failed: {exc}")
            return
        finally:
            # คืน idle เฉพาะตัวที่ยัง collab อยู่ — task จริงที่แทรกมาระหว่างคุยชนะ
            for agent in (a, b):
                current = registry.get(agent.id)
                if current and current.status == "collab":
                    await self._set_status(agent.id, "idle")

        chat_part, _, proposal_part = text.partition(PROPOSAL_MARKER)
        snippet = chat_part.strip().replace("\n", " ")[:CHAT_SNIPPET_CHARS]
        log_service.add("social", f"{a.name}×{b.name}: {snippet}", a.id)
        await ws_manager.broadcast({
            "type": "social.chat",
            "data": {"agent_id": b.id, "partner_id": a.id, "text": snippet},
        })

        proposal_text = proposal_part.strip()
        if proposal_text:
            title = proposal_text.split("\n")[0][:160]
            await proposal_service.create(
                title=title, detail=proposal_text, proposed_by=[a.id, b.id])

    def _run_crew(self, a: AgentConfig, b: AgentConfig) -> str:
        """sync ใน thread — A ชวนคุย, B ตอบ + ตัดสินใจว่ามีไอเดียเสนอไหม"""
        agent_a = Agent(role=a.role, goal=f"คุยงานสบาย ๆ ในฐานะ {a.role}",
                        backstory=a.backstory or f"คุณคือ {a.name} ทีมงาน ET Office",
                        llm=get_llm(a.llm), verbose=False)
        agent_b = Agent(role=b.role, goal=f"คุยงานสบาย ๆ ในฐานะ {b.role}",
                        backstory=b.backstory or f"คุณคือ {b.name} ทีมงาน ET Office",
                        llm=get_llm(b.llm), verbose=False)
        open_task = Task(
            description=(f"คุณคือ {a.name} กำลังพักคุยกับ {b.name} ({b.role}) "
                         "ชวนคุยสั้น ๆ 1-2 ประโยคเกี่ยวกับงานหรือไอเดียพัฒนาทีม/ช่อง"),
            agent=agent_a,
            expected_output="บทพูดสั้น ๆ 1-2 ประโยค (ภาษาไทย)",
        )
        reply_task = Task(
            description=(f"คุณคือ {b.name} ตอบบทสนทนาของ {a.name} สั้น ๆ "
                         "ถ้าระหว่างคุยเกิดไอเดียโปรเจคที่ดีจริง ให้จบข้อความด้วย "
                         f"'{PROPOSAL_MARKER} [สรุปไอเดียหนึ่งย่อหน้า]' "
                         "ถ้าไม่มีไอเดียเด็ดก็จบบทสนทนาเฉย ๆ ไม่ต้องฝืนเสนอ"),
            agent=agent_b,
            context=[open_task],
            expected_output="บทพูดตอบสั้น ๆ อาจจบด้วย PROPOSAL: ถ้ามีไอเดียดี (ภาษาไทย)",
        )
        crew = Crew(agents=[agent_a, agent_b], tasks=[open_task, reply_task],
                    process=Process.sequential, verbose=False)
        result = crew.kickoff()
        return getattr(result, "raw", str(result))

    async def _set_status(self, agent_id: str, status: str) -> None:
        registry.set_status(agent_id, status)
        await ws_manager.broadcast({
            "type": "agent.status",
            "data": {"agent_id": agent_id, "status": status},
        })


social_service = SocialService()
