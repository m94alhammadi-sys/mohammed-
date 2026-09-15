"""منسّق الدورة: التوزيع المتوازي (fan-out) ثم الالتقاء (fan-in).

تدفق الدورة الواحدة:

    المستخدم ──TASK──► المنسّق
                         ├─TASK─► بوالعلوم        ─┐
                         ├─TASK─► المحلل السياسي  ─┤
                         ├─TASK─► المحلل الاقتصادي ─┼─REPORT─► الوكيل التنسيقي
                         ├─TASK─► غرفة العاجل     ─┤
                         └─TASK─► التاجر          ─┘
                                                      │
                                       DECISION ◄─────┘
                                          ▼
                                       المستخدم

كل رسالة تحمل `correlation_id` واحداً، فيمكن استخراج أثر أي قرار كاملاً
من سجل التدقيق في الناقل.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from .agents.base import AGENT_PROFILES, SpecialistAgent
from .agents.chief import ChiefAgent
from .bus import MessageBus, bus as default_bus
from .config import Settings, settings as default_settings
from .llm import LLMClient, llm as default_llm
from .memory import VectorStore
from .schemas import (
    AgentId, AgentReport, ChiefDecision, Envelope, MessageType, new_id,
)

log = logging.getLogger(__name__)

SPECIALISTS: tuple[AgentId, ...] = (
    AgentId.BREAKING,   # الأسرع أولاً — قد يغيّر إطار بقية التحليل
    AgentId.GEO,
    AgentId.MACRO,
    AgentId.FLOW,
    AgentId.SOCIAL,
)

# دالة تُستدعى عند كل تغيّر حالة، لتغذية الواجهة بمؤشر "يكتب الآن".
StatusHook = Callable[[AgentId, str, dict], Awaitable[None]]


class Orchestrator:
    def __init__(
        self,
        llm: LLMClient | None = None,
        memory: VectorStore | None = None,
        message_bus: MessageBus | None = None,
        cfg: Settings | None = None,
    ) -> None:
        self.cfg = cfg or default_settings
        self.llm = llm or default_llm
        self.memory = memory
        self.bus = message_bus or default_bus
        self.agents: dict[AgentId, SpecialistAgent] = {
            agent_id: SpecialistAgent(agent_id, self.llm, memory, self.cfg)
            for agent_id in SPECIALISTS
        }
        self.chief = ChiefAgent(self.llm, memory, self.cfg)
        for agent_id in (*SPECIALISTS, AgentId.CHIEF, AgentId.USER):
            self.bus.register(agent_id)

    # ------------------------------------------------------------ الدورة

    async def run_cycle(
        self,
        topic: str,
        *,
        agents: list[AgentId] | None = None,
        depth: str = "standard",
        status: StatusHook | None = None,
        correlation_id: str | None = None,
    ) -> tuple[ChiefDecision, list[AgentReport]]:
        """ينفّذ دورة تحليل كاملة ويعيد القرار مع التقارير المصدرية."""
        correlation_id = correlation_id or new_id("cyc")
        selected = [a for a in (agents or SPECIALISTS) if a in self.agents]

        await self._emit(
            Envelope(
                correlation_id=correlation_id, sender=AgentId.USER,
                recipients=list(selected), type=MessageType.TASK, topic=topic,
                payload={"topic": topic, "depth": depth},
                trace=["طلب المستخدم لدورة تحليل"],
            )
        )

        # --- التوزيع: كل الوكلاء يعملون بالتوازي ---
        results = await asyncio.gather(
            *(self._run_agent(agent_id, topic, depth, correlation_id, status)
              for agent_id in selected),
            return_exceptions=True,
        )

        reports: list[AgentReport] = []
        for agent_id, result in zip(selected, results):
            if isinstance(result, AgentReport):
                reports.append(result)
            else:
                log.warning("فشل الوكيل %s: %s", agent_id.value, result)
                reports.append(self._failure_report(agent_id, topic, result))

        # --- الالتقاء: الوكيل التنسيقي يركّب القرار ---
        if status:
            await status(AgentId.CHIEF, "synthesizing", {"reports": len(reports)})

        decision = await self.chief.synthesize(topic, reports)

        await self._emit(
            Envelope(
                correlation_id=correlation_id, sender=AgentId.CHIEF,
                recipients=[AgentId.USER], type=MessageType.DECISION, topic=topic,
                payload=decision.model_dump(mode="json"),
                trace=[f"تركيب من {len(reports)} تقريراً",
                       f"ثقة {decision.confidence:.2f}",
                       f"مخاطرة {decision.risk_score:.2f}"],
            )
        )
        if status:
            await status(AgentId.CHIEF, "done", {"decision_id": decision.decision_id})

        return decision, reports

    # ------------------------------------------------------------ وكيل واحد

    async def _run_agent(
        self, agent_id: AgentId, topic: str, depth: str,
        correlation_id: str, status: StatusHook | None,
    ) -> AgentReport:
        if status:
            await status(agent_id, "working", {"topic": topic})
        try:
            report = await asyncio.wait_for(
                self.agents[agent_id].run(topic, depth), timeout=self.cfg.agent_timeout_s
            )
        except asyncio.TimeoutError:
            if status:
                await status(agent_id, "timeout", {})
            raise

        await self._emit(
            Envelope(
                correlation_id=correlation_id, sender=agent_id,
                recipients=[AgentId.CHIEF], type=MessageType.REPORT, topic=topic,
                payload=report.model_dump(mode="json"),
                trace=[f"{len(report.evidence)} دليلاً",
                       f"{len(report.signals)} إشارة",
                       f"ثقة {report.confidence:.2f}"],
            )
        )
        # الأحداث العاجلة عالية الإلحاح تُبثّ فوراً للجميع دون انتظار الدورة
        if agent_id == AgentId.BREAKING and report.urgency >= 0.7:
            await self._emit(
                Envelope(
                    correlation_id=correlation_id, sender=agent_id,
                    recipients=[], type=MessageType.ALERT, topic=topic,
                    payload={"headline": report.headline, "urgency": report.urgency},
                    trace=["تجاوز عتبة الإلحاح 0.70"],
                )
            )
        if status:
            await status(agent_id, "reported", {
                "confidence": report.confidence,
                "evidence": len(report.evidence),
                "degraded": report.degraded,
            })
        return report

    # ------------------------------------------------------------ دردشة

    async def ask_agent(self, agent_id: AgentId, history: list[dict[str, str]]) -> str:
        """سؤال مباشر لوكيل واحد داخل دردشته الخاصة."""
        if agent_id == AgentId.CHIEF:
            system = self.chief.system
            model, effort = self.cfg.chief_model, "medium"
        else:
            agent = self.agents[agent_id]
            system = agent.system
            model, effort = self.cfg.specialist_model, "medium"

        context = ""
        if self.memory:
            last = history[-1]["content"] if history else ""
            hits = self.memory.search(last, k=3, agent_id=agent_id.value)
            if hits:
                context = "\n\n# من تقاريرك السابقة\n" + "\n".join(
                    f"- ({h.ts}) {h.text[:220]}" for h in hits
                )

        return await self.llm.chat(
            system + context + (
                "\n\n# سياق المحادثة\nأنت الآن في دردشة مباشرة مع المستخدم داخل "
                "التطبيق. أجب بإيجاز محادثي (٣–٦ جمل) دون مغادرة اختصاصك، "
                "وبلا JSON. إن كان السؤال خارج اختصاصك فسمِّ الوكيل المناسب."
            ),
            history, model=model, effort=effort,
        )

    # ------------------------------------------------------------ مساعد

    async def _emit(self, env: Envelope) -> None:
        await self.bus.publish(env)

    @staticmethod
    def _failure_report(agent_id: AgentId, topic: str, error: BaseException | object) -> AgentReport:
        """تقرير فشل صريح — الوكيل الغائب يُعلَن غيابه ولا يُحذف بصمت."""
        return AgentReport(
            agent_id=agent_id, topic=topic,
            headline=f"[تعذّر] {AGENT_PROFILES[agent_id].display_name} لم يُكمل مهمته",
            summary=f"انقطعت مهمة الوكيل قبل إنتاج تقرير. السبب: {error}",
            risks=["غياب تغطية هذا المجال في القرار الحالي"],
            data_gaps=[f"لا تغطية لمجال {AGENT_PROFILES[agent_id].tagline}"],
            confidence=0.05, degraded=True,
        )
