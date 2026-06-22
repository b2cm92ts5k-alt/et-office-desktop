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

# M22-3 — บุคลิกต่อ role (preset default ถ้า agent ไม่ได้ตั้ง personality เอง) → คุยเล่นมีสีสัน ไม่จืด
PERSONA_PRESETS: list[tuple[list[str], str]] = [
    (["producer", "manager", "เลขา", "project"], "เป็นทางการนิด ๆ ชอบจัดระเบียบและสรุปเป็นขั้นตอน มองภาพรวมทีม"),
    (["coder", "program", "dev", "วิศวกร", "engineer", "โปรแกรม"], "ตรงไปตรงมา ชอบเหตุผล/ตรรกะ พูดสั้นกระชับสไตล์เทคนิค"),
    # sound ต้องมาก่อน design — "Sound Designer" มีคำว่า "design" จะถูกจับเป็นนักออกแบบผิด
    (["sound", "audio", "เสียง", "music", "ดนตรี", "composer"], "อารมณ์ดี ชอบเปรียบเทียบเรื่องต่าง ๆ กับจังหวะและเสียง"),
    (["design", "ดีไซน์", "ออกแบบ", "artist", "ศิลป", "กราฟิก", "ux"], "ขี้เล่น มีจินตนาการ ชอบพูดถึงสี ความสวยงาม และไอเดียแปลกใหม่"),
    (["research", "วิจัย", "analyst", "ค้นคว้า", "วิเคราะห์"], "ช่างสงสัย ชอบยกข้อมูล/ตัวเลขมาคุย ระมัดระวังก่อนสรุป"),
    (["test", "qa", "tester"], "ละเอียด จับผิดเก่ง ชอบตั้งคำถามว่า 'ถ้า...จะพังไหม'"),
    (["writer", "narrative", "เขียน", "เนื้อเรื่อง"], "ช่างเล่าเรื่อง ใช้ภาษาสละสลวยและมีอารมณ์"),
]
# M22-3 — หัวข้อคุยหมุนเวียน (กันคุยลอย ๆ ซ้ำ ๆ)
TOPICS: list[str] = [
    "ความคืบหน้างานที่ทำอยู่ตอนนี้",
    "ไอเดียพัฒนาทีม/ช่อง ET Office ให้ดีขึ้น",
    "เกม/หนัง/ของที่ชอบช่วงนี้",
    "ชีวิตในออฟฟิศ ET เป็นยังไงบ้าง",
    "เรื่องชื่นชม CEO ETLoLz",
    "เครื่องมือ/เทคนิคใหม่ ๆ ที่น่าลอง",
]
GROUP_CHANCE = 0.35   # โอกาสที่จะเป็นวงคุย 3-4 ตัว (ไม่งั้นคู่ 2 ตัวเหมือนเดิม)
GROUP_MAX = 4
TURN_GAP_SEC = 1.2    # เว้นจังหวะระหว่าง bubble แต่ละคน → ดูเป็นวงสนทนาสลับกันพูด


def personality_of(agent: AgentConfig) -> str:
    """บุคลิกของ agent ตอนคุยเล่น — ตั้งเองใน role .md/agent ก่อน, ไม่งั้น preset ตาม role (M22-3, §5)"""
    own = (getattr(agent, "personality", "") or "").strip()
    if own:
        return own
    hay = (agent.role + " " + " ".join(getattr(agent, "keywords", []) or [])).lower()
    for kws, persona in PERSONA_PRESETS:
        if any(k in hay for k in kws):
            return persona
    return "เป็นกันเอง คุยสบาย ๆ มีอารมณ์ขัน"


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
        # M24-2 — กันเผา quota: social/collab คุยเล่นเป็น cloud call จริง (get_llm(agent.llm))
        # → default ใช้เฉพาะ agent local (ollama=ฟรี); cloud agent ยังทำงาน task ปกติ แค่ไม่คุยเล่นทิ้ง request
        if settings_store.get("social_local_only"):
            idle = [a for a in idle if a.llm.provider == "ollama"]
        if len(idle) < 2 or random.random() >= float(settings_store.get("social_chance")):
            return
        # M22-3 — บางครั้งจับวงคุย 3-4 ตัว (ไม่งั้นคู่ 2 ตัวเหมือนเดิม)
        k = 2
        if len(idle) >= 3 and random.random() < GROUP_CHANCE:
            k = min(len(idle), GROUP_MAX, random.choice([3, 4]))
        group = random.sample(idle, k)
        self._chatting = True
        try:
            await self._run_chat(group)
        finally:
            self._chatting = False

    async def _run_chat(self, group: list[AgentConfig]) -> None:
        """M22-3 — วงคุย 2-4 ตัว: หมุนหัวข้อ + บุคลิกต่อ role + bubble สลับกันพูดทีละคน"""
        ids = [a.id for a in group]
        names = [a.name for a in group]
        topic = random.choice(TOPICS)
        log_service.add("social", f"{' × '.join(names)} จับกลุ่มคุยเรื่อง {topic}", group[0].id)
        await ws_manager.broadcast({
            "type": "social.meetup", "data": {"agents": ids, "names": names},
        })
        for agent in group:
            await self._set_status(agent.id, "collab")

        try:
            lines = await asyncio.to_thread(self._run_crew, group, topic)
        except Exception as exc:  # social พังต้องไม่ล้ม daemon
            log_service.add("error", f"social chat failed: {exc}")
            lines = []
        finally:
            # คืน idle เฉพาะตัวที่ยัง collab อยู่ — task จริงที่แทรกมาระหว่างคุยชนะ
            for agent in group:
                current = registry.get(agent.id)
                if current and current.status == "collab":
                    await self._set_status(agent.id, "idle")

        proposal_text = ""
        for agent, line in lines:
            chat_part, _, prop = line.partition(PROPOSAL_MARKER)
            if prop.strip():
                proposal_text = prop.strip()
            snippet = chat_part.strip().replace("\n", " ")[:CHAT_SNIPPET_CHARS]
            if not snippet:
                continue
            log_service.add("social", f"{agent.name}: {snippet}", agent.id)
            await ws_manager.broadcast({
                "type": "social.chat", "data": {"agent_id": agent.id, "text": snippet},
            })
            await asyncio.sleep(TURN_GAP_SEC)   # สลับจังหวะให้ bubble โผล่ทีละคน เหมือนวงคุย

        if proposal_text:
            title = proposal_text.split("\n")[0][:160]
            await proposal_service.create(title=title, detail=proposal_text, proposed_by=ids)

    def _run_crew(self, group: list[AgentConfig], topic: str) -> list[tuple]:
        """sync ใน thread — วงคุยตามลำดับ แต่ละตัวพูด 1 ที (ตามบุคลิก) → คืน [(agent, line)]

        ตัวสุดท้ายอาจจบด้วย PROPOSAL: ถ้าระหว่างคุยเกิดไอเดียดีจริง. อ่านผลทีละ task
        จาก task.output (กันได้คำพูดของทุกคน ไม่ใช่แค่คนสุดท้าย).
        """
        c_agents: list = []
        c_tasks: list = []
        for i, a in enumerate(group):
            backstory = (a.backstory or f"คุณคือ {a.name} ทีมงาน ET Office") + \
                "\nบุคลิกของคุณ: " + personality_of(a)
            ca = Agent(role=a.role, goal=f"ร่วมวงคุยเล่นสบาย ๆ ในฐานะ {a.role}",
                       backstory=backstory, llm=get_llm(a.llm), verbose=False)
            is_last = i == len(group) - 1
            if i == 0:
                desc = (f"คุณคือ {a.name}. เปิดวงคุยเล่นกับเพื่อนร่วมทีมเรื่อง «{topic}» "
                        "พูดสั้น ๆ 1-2 ประโยคตามบุคลิกของคุณ")
            else:
                desc = (f"คุณคือ {a.name}. ต่อบทสนทนาเรื่อง «{topic}» สั้น ๆ 1-2 ประโยคตามบุคลิกของคุณ"
                        + (f" — ถ้าระหว่างคุยเกิดไอเดียโปรเจคดีจริง จบด้วย '{PROPOSAL_MARKER} [สรุปย่อหน้าเดียว]' "
                           "ไม่งั้นจบเฉย ๆ ไม่ต้องฝืนเสนอ" if is_last else ""))
            t = Task(description=desc, agent=ca,
                     context=([c_tasks[-1]] if c_tasks else []),
                     expected_output="บทพูดสั้น ๆ 1-2 ประโยค (ภาษาไทย)")
            c_agents.append(ca)
            c_tasks.append(t)
        crew = Crew(agents=c_agents, tasks=c_tasks, process=Process.sequential, verbose=False)
        crew.kickoff()
        out: list[tuple] = []
        for a, t in zip(group, c_tasks):
            try:
                raw = getattr(t.output, "raw", "") or str(t.output or "")
            except Exception:  # noqa: BLE001
                raw = ""
            out.append((a, raw))
        return out

    async def _set_status(self, agent_id: str, status: str) -> None:
        registry.set_status(agent_id, status)
        await ws_manager.broadcast({
            "type": "agent.status",
            "data": {"agent_id": agent_id, "status": status},
        })


social_service = SocialService()
