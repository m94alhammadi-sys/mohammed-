"""الوكيل التنسيقي وصانع القرار.

ما يميّزه بنيوياً عن المتخصصين:
  * لا يملك أي موصل بيانات خارجي — مصدره الوحيد تقارير الوكلاء. هذا
    يمنعه من إدخال معلومة من عنده ويجعله مُركِّباً لا مصدراً.
  * الأرقام الحاسمة (ثقة، مخاطرة، تضارب، اتجاه) تُحسب في `synthesis`
    بقواعد حتمية، ثم تُسلَّم للنموذج كقيود لا كاقتراحات.
"""
from __future__ import annotations

import logging

from ..config import Settings, settings as default_settings
from ..llm import LLMClient, LLMError
from ..memory import VectorStore
from ..prompts import system_prompt_for
from ..schemas import (
    AgentId, AgentReport, ChiefDecision, Conflict, DecisionDraft, DecisionOption,
    Direction, Linkage, now_iso,
)
from ..synthesis import (
    aggregate_confidence, consensus_stance, dedupe_evidence, detect_conflicts,
    quality_flags, risk_score,
)

log = logging.getLogger(__name__)


class ChiefAgent:
    def __init__(
        self,
        llm: LLMClient,
        memory: VectorStore | None = None,
        cfg: Settings | None = None,
    ) -> None:
        self.agent_id = AgentId.CHIEF
        self.llm = llm
        self.memory = memory
        self.cfg = cfg or default_settings
        self.system = system_prompt_for(AgentId.CHIEF)

    async def synthesize(self, topic: str, reports: list[AgentReport]) -> ChiefDecision:
        # --- 1) الحساب الحتمي أولاً، قبل أي كلمة من النموذج ---
        stance = consensus_stance(reports)
        conflicts = detect_conflicts(reports)
        confidence, confidence_trace = aggregate_confidence(
            reports, conflicts, stance=stance
        )
        risk = risk_score(reports, conflicts)
        flags = quality_flags(reports, conflicts)
        sources = dedupe_evidence(reports)

        # --- 2) النموذج يكتب التحليل ضمن هذه القيود ---
        draft, synthesized = await self._draft(
            topic, reports, stance, conflicts, confidence, risk, flags
        )

        # لا تحليل = لا ثقة. القرار الذي لم يُركَّب فعلياً لا يجوز أن يحمل
        # ثقة محسوبة من تقارير لم يقرأها أحد.
        if not synthesized:
            confidence = min(confidence, 0.10)
            flags = flags + ["⚠ لم يُركَّب القرار عبر النموذج — الثقة مُصفّرة قسراً"]

        # --- 3) الأرقام المحسوبة تتغلب على أرقام النموذج ---
        decision = ChiefDecision(
            topic=topic,
            situation=draft.situation,
            linkages=[
                Linkage(
                    cause=l.cause, effect=l.effect, channel=l.channel,
                    agents_involved=[
                        AgentId(a) for a in l.agents_involved if a in AgentId._value2member_map_
                    ],
                    strength=l.strength,
                )
                for l in draft.linkages
            ],
            conflicts=self._merge_conflicts(conflicts, draft),
            recommendation=draft.recommendation,
            stance=stance.direction,
            confidence=confidence,
            risk_score=risk,
            options=[
                DecisionOption(
                    label=o.label, action=o.action, rationale=o.rationale,
                    risk_level=o.risk_level, expected_impact=o.expected_impact,
                    invalidation=o.invalidation,
                )
                for o in draft.options
            ],
            invalidation_triggers=draft.invalidation_triggers,
            watchlist=draft.watchlist,
            sources_used=sources[:25],
            agent_confidences={r.agent_id.value: r.confidence for r in reports},
            quality_flags=flags + [f"سلسلة حساب الثقة: {' ← '.join(confidence_trace)}"],
        )
        self._remember(decision)
        return decision

    # ------------------------------------------------------------ النموذج

    async def _draft(
        self, topic: str, reports: list[AgentReport], stance, conflicts: list[Conflict],
        confidence: float, risk: float, flags: list[str],
    ) -> tuple[DecisionDraft, bool]:
        """يعيد المسودة مع علم يقول هل جرى تركيب حقيقي أم مخرج بديل."""
        if not self.llm.enabled:
            return self._offline_draft(topic, reports, flags), False
        try:
            draft = await self.llm.structure(
                self.system,
                self._prompt(topic, reports, stance, conflicts, confidence, risk, flags),
                DecisionDraft,
                model=self.cfg.chief_model,
                effort=self.cfg.chief_effort,
            )
            return draft, True
        except LLMError as exc:
            log.warning("فشل تركيب القرار: %s", exc)
            draft = self._offline_draft(topic, reports, flags)
            draft.situation = f"تعذّر تركيب القرار عبر النموذج: {exc}"
            return draft, False

    def _prompt(
        self, topic: str, reports: list[AgentReport], stance, conflicts: list[Conflict],
        confidence: float, risk: float, flags: list[str],
    ) -> str:
        blocks: list[str] = [
            f"# الموضوع\n{topic}",
            f"\n# التوقيت\n{now_iso()} (UTC)",
            "\n# التقارير الواردة من الوكلاء المتخصصين",
        ]

        for report in reports:
            evidence_lines = "\n".join(
                f"    [{i}] ({e.source_type} | {e.reliability:.2f}) {e.title} — {e.url or '—'}"
                for i, e in enumerate(report.evidence[:10])
            ) or "    (لا أدلة)"
            signal_lines = "\n".join(
                f"    - {s.name} | {s.direction.value} | قوة {s.strength:.2f} | "
                f"أفق {s.horizon.value} | أصول: {', '.join(s.asset_classes) or 'عام'} | "
                f"أدلة {s.evidence_refs or 'بلا'} | {s.rationale}"
                for s in report.signals
            ) or "    (لا إشارات)"

            blocks.append(
                f"\n## {report.agent_id.value}"
                f"{' ⚠ منقطع عن المصادر' if report.degraded else ''}\n"
                f"العنوان: {report.headline}\n"
                f"الثقة المعلنة: {report.confidence:.2f} | الإلحاح: {report.urgency:.2f}\n"
                f"الملخص: {report.summary}\n"
                f"الإشارات:\n{signal_lines}\n"
                f"المخاطر: {'؛ '.join(report.risks) or '—'}\n"
                f"فجوات البيانات: {'؛ '.join(report.data_gaps) or '—'}\n"
                f"ادعاءات غير مؤكدة: {'؛ '.join(report.unverified_claims) or '—'}\n"
                f"الأدلة:\n{evidence_lines}"
            )

        conflict_lines = "\n".join(
            f"- [{c.severity:.2f}] {c.topic}: {c.agent_a.value} يقول «{c.claim_a}» "
            f"بينما {c.agent_b.value} يقول «{c.claim_b}»"
            for c in conflicts
        ) or "(لم يُكتشف تضارب بنيوي آلياً — ابحث عن تضارب دلالي بنفسك)"

        blocks.append(
            "\n# نتائج المحرك الحتمي (مُلزِمة — لا تعدّلها)\n"
            f"- الاتجاه المرجّح: {stance.direction.value} (درجة {stance.score:+.2f}، "
            f"اتفاق {stance.agreement:.0%})\n"
            f"- الثقة النهائية المحسوبة: {confidence:.2f}\n"
            f"- درجة المخاطرة المحسوبة: {risk:.2f}\n"
            f"- تصويت الوكلاء: {stance.voters}\n"
            f"\n# التضارب المكتشف آلياً\n{conflict_lines}\n"
            f"\n# أعلام الجودة\n" + ("\n".join(f"- {f}" for f in flags) or "- لا شيء")
        )

        blocks.append(
            "\n# المطلوب\n"
            "أنتج التقرير التنفيذي. قيود إلزامية:\n"
            "1. استخدم قيمتَي `confidence` و`risk_score` المحسوبتين أعلاه حرفياً.\n"
            "2. لكل تضارب مكتشف، اكتب `resolution` تذكر فيه المعيار الذي حسمت به "
            "(قرب المصدر / رسمية المصدر / حداثة البيان)، أو صرّح بأنه غير محسوم.\n"
            "3. `linkages`: كل رابط يحتاج قناة انتقال مسماة ووكلاء يسندونه.\n"
            "4. `options`: ثلاثة خيارات على الأقل، أحدها دائماً «الانتظار وعدم الفعل».\n"
            "5. `invalidation_triggers`: لا تترك القائمة فارغة أبداً.\n"
            "6. لا تُدخل أي معلومة غير واردة في التقارير أعلاه. الناقص يذهب "
            "إلى `watchlist`.\n"
            "7. إن كانت الأدلة ضعيفة أو أعلام الجودة تحذيرية، فالتوصية الصحيحة "
            "هي تأجيل القرار مع تحديد البيانات المطلوبة."
        )
        return "\n".join(blocks)

    # ------------------------------------------------------------ بدائل

    @staticmethod
    def _offline_draft(
        topic: str, reports: list[AgentReport], flags: list[str],
    ) -> DecisionDraft:
        return DecisionDraft(
            situation=(
                f"تعذّر إنتاج تقرير تنفيذي عن «{topic}»: النموذج اللغوي غير مفعّل. "
                f"وصل {len(reports)} تقريراً، وعدد الأدلة الخام "
                f"{sum(len(r.evidence) for r in reports)}."
            ),
            linkages=[],
            conflicts=[],
            recommendation="لا قرار. المنظومة تعمل في وضع منقطع ولا يجوز بناء قرار عليها.",
            stance=Direction.NEUTRAL,
            confidence=0.05,
            risk_score=0.5,
            options=[],
            invalidation_triggers=["تفعيل ANTHROPIC_API_KEY وإعادة تشغيل الدورة"],
            watchlist=flags,
        )

    @staticmethod
    def _merge_conflicts(detected: list[Conflict], draft: DecisionDraft) -> list[Conflict]:
        """يدمج حسم النموذج مع التضارب المكتشف آلياً.

        التضارب المكتشف يبقى في القائمة حتى لو تجاهله النموذج — إخفاء
        التضارب ممنوع بنيوياً لا بالتعليمات فقط.
        """
        resolutions = {
            (d.agent_a, d.agent_b, d.topic.strip().lower()): d.resolution
            for d in draft.conflicts
        }
        out: list[Conflict] = []
        for conflict in detected:
            key = (conflict.agent_a.value, conflict.agent_b.value, conflict.topic)
            reverse = (conflict.agent_b.value, conflict.agent_a.value, conflict.topic)
            conflict.resolution = (
                resolutions.get(key) or resolutions.get(reverse) or "غير محسوم — يحتاج بيانات إضافية"
            )
            out.append(conflict)

        known = {(c.agent_a.value, c.agent_b.value, c.topic) for c in out}
        for extra in draft.conflicts:
            key = (extra.agent_a, extra.agent_b, extra.topic.strip().lower())
            if key in known:
                continue
            try:
                out.append(Conflict(
                    topic=extra.topic, agent_a=AgentId(extra.agent_a),
                    agent_b=AgentId(extra.agent_b), claim_a=extra.claim_a,
                    claim_b=extra.claim_b, severity=extra.severity,
                    resolution=extra.resolution,
                ))
            except ValueError:
                log.info("تجاهل تضارب بمعرّف وكيل غير معروف: %s", key)
        return out

    def _remember(self, decision: ChiefDecision) -> None:
        if not self.memory:
            return
        self.memory.upsert(
            doc_id=decision.decision_id,
            agent_id=AgentId.CHIEF.value,
            topic=decision.topic,
            text=f"{decision.situation}\n{decision.recommendation}",
            ts=decision.created_at,
            meta={"confidence": decision.confidence, "risk": decision.risk_score,
                  "stance": decision.stance.value},
        )
