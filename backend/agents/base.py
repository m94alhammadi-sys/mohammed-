"""الوكيل المتخصص: دورة حياة موحّدة لكل الوكلاء الخمسة.

دورة الوكيل: استقبال مهمة -> جمع مصادر -> بحث موجّه -> هيكلة التقرير
-> نشره على الناقل. ما يختلف بين الوكلاء هو البرومبت والمصادر فقط،
وهذا مقصود: الاختصاص بيانات وتعليمات، لا كود مكرر خمس مرات.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..config import Settings, settings as default_settings
from ..llm import LLMClient, LLMError
from ..memory import VectorStore
from ..prompts import system_prompt_for
from ..schemas import (
    AgentId, AgentReport, Evidence, ReportDraft, Signal, now_iso,
)
from ..tools import ConnectorResult, gather_context

log = logging.getLogger(__name__)


@dataclass
class AgentProfile:
    agent_id: AgentId
    display_name: str
    handle: str              # الاسم الذي يظهر في واجهة الدردشة
    avatar: str              # حرف/رمز للصورة الرمزية
    color: str
    tagline: str
    # نطاقات يُفضَّل البحث ضمنها (تُمرَّر لأداة البحث الخادمية)
    preferred_domains: list[str] = field(default_factory=list)


AGENT_PROFILES: dict[AgentId, AgentProfile] = {
    AgentId.SOCIAL: AgentProfile(
        AgentId.SOCIAL, "بوالعلوم", "بوالعلوم", "بع", "#25D366",
        "مشاعر الجمهور والمواضيع الرائجة",
        ["reddit.com", "x.com", "linkedin.com", "youtube.com"],
    ),
    AgentId.GEO: AgentProfile(
        AgentId.GEO, "المحلل السياسي", "المحلل السياسي", "سي", "#8E44AD",
        "الجيوسياسة وقرارات الحكومات",
        ["reuters.com", "apnews.com", "aljazeera.net", "un.org", "europa.eu"],
    ),
    AgentId.MACRO: AgentProfile(
        AgentId.MACRO, "المحلل الاقتصادي", "المحلل الاقتصادي", "اق", "#2980B9",
        "التضخم والفائدة والبنوك المركزية",
        ["federalreserve.gov", "ecb.europa.eu", "imf.org", "bls.gov", "bis.org"],
    ),
    AgentId.BREAKING: AgentProfile(
        AgentId.BREAKING, "غرفة العاجل", "غرفة العاجل", "عا", "#E74C3C",
        "الأحداث الطارئة لحظة بلحظة",
        ["reuters.com", "apnews.com", "bbc.com"],
    ),
    AgentId.FLOW: AgentProfile(
        AgentId.FLOW, "التاجر", "التاجر", "تج", "#F39C12",
        "تدفقات السيولة وحركة الحيتان",
        ["sec.gov", "bloomberg.com", "reuters.com", "cftc.gov"],
    ),
    AgentId.CHIEF: AgentProfile(
        AgentId.CHIEF, "الوكيل التنسيقي", "مجلس القرار", "قر", "#075E54",
        "يربط الخيوط ويصنع القرار",
    ),
}


class SpecialistAgent:
    """وكيل متخصص واحد."""

    def __init__(
        self,
        agent_id: AgentId,
        llm: LLMClient,
        memory: VectorStore | None = None,
        cfg: Settings | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.profile = AGENT_PROFILES[agent_id]
        self.llm = llm
        self.memory = memory
        self.cfg = cfg or default_settings
        self.system = system_prompt_for(agent_id)

    # ------------------------------------------------------------ التنفيذ

    async def run(self, topic: str, depth: str = "standard") -> AgentReport:
        """ينفّذ دورة كاملة ويعيد تقريراً معيارياً."""
        connector_results = await gather_context(self.agent_id, topic)
        evidence = [e for r in connector_results if r.ok for e in r.evidence]
        failures = [r for r in connector_results if not r.ok]

        research_text = ""
        web_evidence: list[Evidence] = []
        used_web = False

        if self.llm.enabled and depth != "quick":
            research = await self.llm.research(
                self.system,
                self._research_prompt(topic, connector_results),
                effort=self._effort(depth),
                allowed_domains=self.profile.preferred_domains or None,
            )
            research_text = research.text
            web_evidence = research.evidence
            used_web = research.used_web

        evidence = self._merge_evidence(evidence, web_evidence)
        degraded = not evidence and not used_web

        draft = await self._draft(topic, research_text, evidence, failures, depth)
        report = self._assemble(topic, draft, evidence, degraded, failures, used_web)
        self._remember(report)
        return report

    def _effort(self, depth: str) -> str:
        return {"quick": "low", "standard": self.cfg.specialist_effort, "deep": "xhigh"}[depth]

    # ------------------------------------------------------------ البرومبت

    def _research_prompt(self, topic: str, results: list[ConnectorResult]) -> str:
        lines = [
            f"# الموضوع قيد التحليل\n{topic}",
            f"\n# التوقيت الحالي\n{now_iso()} (UTC)",
            "\n# ما وصلك من موصلات البيانات الخاصة بك",
        ]
        for result in results:
            if result.ok:
                lines.append(f"\n## ✅ {result.name} — {result.note}")
                for index, item in enumerate(result.evidence, 1):
                    lines.append(
                        f"{index}. [{item.publisher or '—'} | موثوقية {item.reliability:.2f}] "
                        f"{item.title}\n   {item.url or ''}\n   {item.excerpt[:220]}"
                    )
            else:
                lines.append(f"\n## ❌ {result.name} — غير متاح: {result.note}")

        if self.memory:
            prior = self.memory.search(topic, k=3, agent_id=self.agent_id.value)
            if prior:
                lines.append("\n# ما سبق أن قلتَه عن هذا الموضوع")
                for hit in prior:
                    lines.append(f"- ({hit.ts}) {hit.text[:260]}")

        lines.append(
            "\n# المطلوب الآن\n"
            "ابحث بعمق في اختصاصك أنت فقط. استخدم أداة البحث للتحقق من الوقائع "
            "وسدّ الفجوات التي تركتها الموصلات غير المتاحة. اكتب نتيجة البحث "
            "نصاً تحليلياً مكثفاً، واذكر لكل واقعة مصدرها. إذا لم تجد مصدراً "
            "لواقعة، قل ذلك صراحة ولا تكملها من معرفتك العامة."
        )
        return "\n".join(lines)

    def _structure_prompt(
        self, topic: str, research_text: str,
        evidence: list[Evidence], failures: list[ConnectorResult],
    ) -> str:
        catalogue = "\n".join(
            f"[{i}] ({item.source_type} | موثوقية {item.reliability:.2f}) "
            f"{item.title} — {item.publisher or '—'} {item.url or ''}"
            for i, item in enumerate(evidence)
        ) or "(لا أدلة مُثبتة)"

        blind = "\n".join(f"- {f.name}: {f.note}" for f in failures) or "(لا شيء)"

        return (
            f"# الموضوع\n{topic}\n\n"
            f"# نتيجة بحثك الخام\n{research_text or '(لم يُجرَ بحث حي)'}\n\n"
            f"# فهرس الأدلة المتاحة لك (استخدم هذه الفهارس في evidence_refs)\n{catalogue}\n\n"
            f"# مصادر كنت أعمى عنها في هذه الدورة\n{blind}\n\n"
            "# المطلوب\n"
            "حوّل ما سبق إلى تقريرك المعياري. قيود إلزامية:\n"
            "1. كل إشارة في `signals` تشير إلى فهرس دليل واحد على الأقل في "
            "`evidence_refs`، ولا تخترع فهارس غير موجودة أعلاه.\n"
            "2. ضع كل واقعة بلا دليل في `unverified_claims` لا في `summary`.\n"
            "3. أدرج كل مصدر أعمى في `data_gaps` بصياغة تشرح أثره على قراءتك.\n"
            "4. عايِر `confidence` وفق سلّم الثقة في تعليماتك، لا وفق قوة حدسك.\n"
            "5. لا توصية شراء أو بيع — الرصد فقط."
        )

    # ------------------------------------------------------------ الهيكلة

    async def _draft(
        self, topic: str, research_text: str,
        evidence: list[Evidence], failures: list[ConnectorResult], depth: str,
    ) -> ReportDraft:
        if not self.llm.enabled:
            return self._offline_draft(topic, evidence, failures)
        try:
            return await self.llm.structure(
                self.system,
                self._structure_prompt(topic, research_text, evidence, failures),
                ReportDraft,
                effort=self._effort(depth),
            )
        except LLMError as exc:
            log.warning("[%s] فشلت الهيكلة: %s", self.agent_id.value, exc)
            draft = self._offline_draft(topic, evidence, failures)
            draft.notes = f"فشل توليد التقرير عبر النموذج: {exc}"
            return draft

    def _offline_draft(
        self, topic: str, evidence: list[Evidence], failures: list[ConnectorResult],
    ) -> ReportDraft:
        """مخرج بديل موسوم بوضوح — لا يدّعي تحليلاً لم يحدث."""
        return ReportDraft(
            headline=f"[وضع منقطع] {self.profile.display_name}: لا تحليل متاح لـ «{topic}»",
            summary=(
                f"لم يُنتَج تحليل لغوي لأن النموذج غير مفعّل أو تعذّر استدعاؤه. "
                f"عدد الأدلة الخام التي أمكن جلبها: {len(evidence)}. "
                f"هذا مخرج بديل ولا يُبنى عليه قرار."
            ),
            signals=[],
            risks=["التقرير بديل ولا يعكس تحليلاً فعلياً"],
            data_gaps=[f"{f.name}: {f.note}" for f in failures]
            or ["النموذج اللغوي غير مفعّل"],
            unverified_claims=[],
            confidence=0.05,
            urgency=0.0,
            notes="أضف ANTHROPIC_API_KEY في .env لتشغيل التحليل الحقيقي.",
        )

    # ------------------------------------------------------------ التجميع

    def _assemble(
        self, topic: str, draft: ReportDraft, evidence: list[Evidence],
        degraded: bool, failures: list[ConnectorResult], used_web: bool,
    ) -> AgentReport:
        max_index = len(evidence) - 1
        signals = [
            Signal(
                name=s.name, direction=s.direction, strength=s.strength,
                horizon=s.horizon, asset_classes=s.asset_classes, rationale=s.rationale,
                # تنظيف الفهارس المخترعة: إشارة تحيل إلى دليل غير موجود
                # تفقد إحالتها بدل أن تمرّ كأنها مسنودة.
                evidence_refs=[i for i in s.evidence_refs if 0 <= i <= max_index],
            )
            for s in draft.signals
        ]

        gaps = list(draft.data_gaps)
        for failure in failures:
            entry = f"{failure.name}: {failure.note}"
            if entry not in gaps:
                gaps.append(entry)

        unsourced = [s.name for s in signals if not s.evidence_refs]
        unverified = list(draft.unverified_claims)
        if unsourced:
            unverified.append(
                "إشارات بلا دليل مُثبت: " + "، ".join(unsourced)
            )

        confidence = draft.confidence
        if degraded:
            confidence = min(confidence, 0.25)

        return AgentReport(
            agent_id=self.agent_id,
            topic=topic,
            headline=draft.headline,
            summary=draft.summary,
            signals=signals,
            evidence=evidence,
            risks=draft.risks,
            data_gaps=gaps,
            unverified_claims=unverified,
            confidence=round(confidence, 4),
            urgency=draft.urgency,
            degraded=degraded,
            notes=draft.notes + ("" if used_web else " | لم يُستخدم بحث حي."),
        )

    # ------------------------------------------------------------ الذاكرة

    def _remember(self, report: AgentReport) -> None:
        if not self.memory:
            return
        self.memory.upsert(
            doc_id=report.report_id,
            agent_id=self.agent_id.value,
            topic=report.topic,
            text=f"{report.headline}\n{report.summary}",
            ts=report.created_at,
            meta={"confidence": report.confidence, "signals": len(report.signals)},
        )

    # ------------------------------------------------------------ مساعد

    @staticmethod
    def _merge_evidence(primary: list[Evidence], extra: list[Evidence]) -> list[Evidence]:
        merged: dict[str, Evidence] = {e.key(): e for e in primary}
        for item in extra:
            merged.setdefault(item.key(), item)
        return sorted(merged.values(), key=lambda e: e.reliability, reverse=True)
