"""يزرع دورة عرض توضيحي في قاعدة البيانات لرؤية الواجهة بلا مفتاح API.

⚠ كل ما يزرعه هذا السكربت بيانات توضيحية مُصطنعة موسومة صراحة، وليست
تحليلاً حقيقياً ولا مصادر حقيقية. الغرض منه عرض الواجهة فقط.

    python3 scripts/demo_seed.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agents.chief import ChiefAgent                          # noqa: E402
from backend.config import settings                                  # noqa: E402
from backend.formatting import decision_to_text, report_to_text      # noqa: E402
from backend.schemas import (                                        # noqa: E402
    AgentId, AgentReport, ChatMessage, DecisionDraft, Direction, Evidence,
    Horizon, LinkageDraft, OptionDraft, Signal,
)
from backend.store import ChatStore                                  # noqa: E402

TOPIC = "[عرض توضيحي] أثر قرار الفائدة القادم على الذهب"
MARK = "⚠ بيانات عرض توضيحي مُصطنعة — ليست تحليلاً ولا مصادر حقيقية."


def ev(title: str, publisher: str, reliability: float, source="news") -> Evidence:
    return Evidence(
        source_type=source, title=f"[توضيحي] {title}", url="https://example.invalid/demo",
        publisher=publisher, published_at="2026-09-15", reliability=reliability,
        excerpt="عنصر توضيحي لعرض شكل الواجهة.",
    )


def sig(name, direction, strength, assets, rationale, refs=(0,)) -> Signal:
    return Signal(name=name, direction=direction, strength=strength, horizon=Horizon.SHORT,
                  asset_classes=list(assets), rationale=rationale, evidence_refs=list(refs))


REPORTS: list[AgentReport] = [
    AgentReport(
        agent_id=AgentId.BREAKING, topic=TOPIC,
        headline="لا أحداث طارئة مؤثرة خلال آخر ٦ ساعات",
        summary=f"{MARK} لم يُرصد حدث غير مجدول يغيّر إطار التسعير الحالي.",
        signals=[], evidence=[ev("لا تنبيهات عاجلة", "وكالة توضيحية", 0.8)],
        risks=[], data_gaps=[], confidence=0.62, urgency=0.1,
    ),
    AgentReport(
        agent_id=AgentId.GEO, topic=TOPIC,
        headline="توتر إقليمي مستقر بلا تصعيد جديد",
        summary=f"{MARK} لا قرارات حكومية جديدة تمسّ تدفقات المعادن هذا الأسبوع.",
        signals=[sig("علاوة المخاطر الجيوسياسية", Direction.BULLISH, 0.45,
                     ["الذهب"], "الطلب على الملاذ الآمن يبقى قائماً بلا تصعيد")],
        evidence=[ev("بيان دبلوماسي توضيحي", "مصدر رسمي توضيحي", 0.9, "official")],
        risks=["تصعيد مفاجئ يعيد تسعير علاوة المخاطر"],
        data_gaps=["لا تغطية للتصريحات غير المنشورة"], confidence=0.58,
    ),
    AgentReport(
        agent_id=AgentId.MACRO, topic=TOPIC,
        headline="السوق يسعّر ثباتاً في الفائدة مع لهجة متشددة",
        summary=f"{MARK} القراءة التوضيحية: تضخم أعلى من المستهدف وسيولة متشددة.",
        signals=[sig("مسار الفائدة الحقيقية", Direction.BEARISH, 0.72, ["الذهب"],
                     "ارتفاع العائد الحقيقي يرفع كلفة الاحتفاظ بأصل بلا عائد")],
        evidence=[ev("محضر اجتماع توضيحي", "بنك مركزي توضيحي", 0.95, "official")],
        risks=["مفاجأة تضخمية تقلب التسعير"],
        data_gaps=["بيانات التضخم الشهرية غير متاحة في وضع العرض"], confidence=0.71,
    ),
    AgentReport(
        agent_id=AgentId.FLOW, topic=TOPIC,
        headline="تجميع مؤسسي هادئ قرب الدعم مع حجم مؤكِّد",
        summary=f"{MARK} تدفق توضيحي يظهر تراكماً عند المستويات الدنيا.",
        signals=[sig("تجميع مؤسسي", Direction.BULLISH, 0.68, ["الذهب"],
                     "زيادة الحجم عند الدعم دون كسره")],
        evidence=[ev("تدفقات صناديق توضيحية", "مزود بيانات توضيحي", 0.8, "market_data")],
        risks=["ازدحام التموضع في اتجاه واحد يرفع خطر الانعكاس"],
        data_gaps=["بيانات الصفقات الكتلية غير متاحة بلا اشتراك"], confidence=0.66,
    ),
    AgentReport(
        agent_id=AgentId.SOCIAL, topic=TOPIC,
        headline="زخم نقاش مرتفع بلا تحول في الاتجاه — ضجيج محتمل",
        summary=f"{MARK} حجم النقاش ارتفع دون تغيّر في التوزيع العاطفي.",
        signals=[sig("زخم النقاش", Direction.NEUTRAL, 0.4, ["الذهب"],
                     "ارتفاع الحجم بلا تحول اتجاه = ضجيج")],
        evidence=[ev("عينة منشورات توضيحية", "منصة توضيحية", 0.35, "social")],
        risks=["احتمال تضخيم منسّق"],
        data_gaps=["لا وصول إلى X ولا YouTube بلا مفاتيح"],
        unverified_claims=["شائعة متداولة بلا تأكيد رسمي"], confidence=0.41,
    ),
]

DRAFT = DecisionDraft(
    situation=(f"{MARK} إشارتان متعاكستان على الذهب: العائد الحقيقي ضاغط هبوطاً، "
               "بينما التدفق المؤسسي والطلب على الملاذ الآمن يسندان صعوداً."),
    linkages=[
        LinkageDraft(cause="لهجة نقدية متشددة", effect="ضغط هبوطي على الذهب",
                     channel="العائد الحقيقي وكلفة الفرصة",
                     agents_involved=["economic_analyst", "the_trader"], strength=0.72),
        LinkageDraft(cause="استمرار التوتر الإقليمي", effect="أرضية سعرية للذهب",
                     channel="الطلب على الملاذ الآمن",
                     agents_involved=["political_analyst", "the_trader"], strength=0.45),
    ],
    conflicts=[], recommendation=(
        "لا فتح مركز اتجاهي الآن. القرار التنفيذي: الانتظار حتى صدور قرار الفائدة، "
        "لأن التضارب بين العائد الحقيقي والتدفق المؤسسي غير محسوم ولا تكفي الأدلة الحالية "
        "لترجيح أحد الطرفين."),
    stance=Direction.NEUTRAL, confidence=0.55, risk_score=0.42,
    options=[
        OptionDraft(label="الانتظار وعدم الفعل", action="لا تغيير في التموضع حتى القرار",
                    rationale="التضارب غير محسوم والثقة دون العتبة", risk_level="low",
                    expected_impact="تفويت حركة أولى محتملة مقابل تجنب خطأ اتجاهي",
                    invalidation="حسم التضارب بعد صدور القرار"),
        OptionDraft(label="تموضع جزئي عند الدعم", action="شريحة صغيرة مع وقف تحت الدعم",
                    rationale="التجميع المؤسسي مسنود بحجم مؤكِّد", risk_level="medium",
                    expected_impact="مشاركة محدودة في السيناريو الصاعد",
                    invalidation="كسر الدعم بحجم مرتفع"),
        OptionDraft(label="تحوّط ضد سيناريو التشدد", action="تحوّط محدود الكلفة",
                    rationale="العائد الحقيقي أقوى إشارة مرجّحة حالياً", risk_level="high",
                    expected_impact="حماية من هبوط حاد بكلفة معلومة",
                    invalidation="لهجة نقدية أكثر ليونة من المتوقع"),
    ],
    invalidation_triggers=[
        "صدور قرار فائدة مخالف للتسعير الحالي",
        "كسر مستوى الدعم بحجم يفوق متوسط عشر جلسات",
        "تصعيد جيوسياسي يغيّر علاوة المخاطر",
    ],
    watchlist=["بيانات التضخم القادمة", "تدفقات الصناديق الأسبوعية",
               "الصفقات الكتلية غير المتاحة حالياً"],
)


class _SeedLLM:
    """يستبدل نداء النموذج بمسودة توضيحية ثابتة، مع إبقاء الحساب الحتمي حقيقياً."""

    enabled = True

    async def structure(self, system, prompt, schema_cls, **kwargs):
        return DRAFT


async def main() -> None:
    store = ChatStore(settings.db_path)
    store.clear_chat("war_room")

    decision = await ChiefAgent(_SeedLLM()).synthesize(TOPIC, REPORTS)

    store.add_message(ChatMessage(chat_id="war_room", author="user", text=TOPIC))
    store.add_message(ChatMessage(
        chat_id="war_room", author=AgentId.CHIEF.value, kind="system",
        text=f"{MARK} بدأت دورة تحليل — وُزّعت المهمة على 5 وكلاء.",
    ))
    for report in REPORTS:
        store.add_message(ChatMessage(
            chat_id="war_room", author=report.agent_id.value, kind="report",
            text=report_to_text(report),
            meta={"confidence": report.confidence, "evidence": len(report.evidence),
                  "degraded": report.degraded, "urgency": report.urgency},
        ))
    store.save_decision(decision.decision_id, decision.topic, decision.created_at,
                        decision.model_dump(mode="json"))
    store.add_message(ChatMessage(
        chat_id="war_room", author=AgentId.CHIEF.value, kind="decision",
        text=decision_to_text(decision),
        meta={"decision_id": decision.decision_id, "confidence": decision.confidence,
              "risk": decision.risk_score, "stance": decision.stance.value},
    ))

    print(f"تم زرع دورة عرض توضيحي في {settings.db_path}")
    print(f"الثقة المحسوبة حتمياً: {decision.confidence:.2f} | "
          f"المخاطرة: {decision.risk_score:.2f} | الاتجاه: {decision.stance.value}")
    print(MARK)


if __name__ == "__main__":
    asyncio.run(main())
