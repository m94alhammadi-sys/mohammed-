"""اختبارات الوكيل المتخصص والوكيل التنسيقي."""
import pytest

from backend.agents.base import SpecialistAgent
from backend.agents.chief import ChiefAgent
from backend.schemas import AgentId, Direction, Evidence
from tests.factories import report, signal
from tests.fakes import (
    FakeLLM, dead_connector, default_decision_draft, default_report_draft, ok_connector,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def connectors(monkeypatch):
    """يسمح لكل اختبار بتحديد ما تعيده الموصلات بلا أي شبكة."""
    box = {"results": [ok_connector()]}

    async def fake_gather(agent_id, topic):
        return box["results"]

    monkeypatch.setattr("backend.agents.base.gather_context", fake_gather)
    return box


class TestSpecialistAgent:
    async def test_produces_report_with_evidence(self, connectors):
        agent = SpecialistAgent(AgentId.FLOW, FakeLLM())
        result = await agent.run("الذهب")
        assert result.agent_id is AgentId.FLOW
        assert len(result.evidence) == 2
        assert result.degraded is False
        assert result.confidence == pytest.approx(0.75)

    async def test_dead_connectors_become_declared_data_gaps(self, connectors):
        connectors["results"] = [dead_connector("news:geo", "الشبكة محجوبة")]
        agent = SpecialistAgent(AgentId.GEO, FakeLLM())
        result = await agent.run("الذهب")
        assert any("news:geo" in gap for gap in result.data_gaps)

    async def test_no_sources_at_all_marks_degraded_and_caps_confidence(self, connectors):
        connectors["results"] = [dead_connector()]
        agent = SpecialistAgent(AgentId.GEO, FakeLLM(research_evidence=[]))
        result = await agent.run("الذهب")
        assert result.degraded is True
        assert result.confidence <= 0.25

    async def test_web_evidence_merges_with_connector_evidence(self, connectors):
        web = [Evidence(source_type="web", title="ويب", url="https://web.test/1",
                        reliability=0.6)]
        agent = SpecialistAgent(AgentId.GEO, FakeLLM(research_evidence=web))
        result = await agent.run("الذهب")
        urls = {e.url for e in result.evidence}
        assert "https://web.test/1" in urls and "https://example.com/0" in urls

    async def test_duplicate_sources_are_deduplicated(self, connectors):
        same = [Evidence(source_type="web", title="مكرر",
                         url="https://example.com/0", reliability=0.9)]
        agent = SpecialistAgent(AgentId.FLOW, FakeLLM(research_evidence=same))
        result = await agent.run("الذهب")
        assert len(result.evidence) == 2

    async def test_invented_evidence_refs_are_stripped(self, connectors):
        """إشارة تحيل إلى دليل غير موجود تفقد إحالتها بدل أن تبدو مسنودة."""
        draft = default_report_draft()
        draft.signals[0].evidence_refs = [0, 99, -3]
        agent = SpecialistAgent(AgentId.FLOW, FakeLLM(report=draft))
        result = await agent.run("الذهب")
        assert result.signals[0].evidence_refs == [0]

    async def test_signal_without_evidence_is_flagged_unverified(self, connectors):
        draft = default_report_draft()
        draft.signals[0].evidence_refs = []
        agent = SpecialistAgent(AgentId.FLOW, FakeLLM(report=draft))
        result = await agent.run("الذهب")
        assert any("بلا دليل" in claim for claim in result.unverified_claims)

    async def test_llm_failure_falls_back_to_marked_report(self, connectors):
        agent = SpecialistAgent(AgentId.FLOW, FakeLLM(fail_structure=True))
        result = await agent.run("الذهب")
        assert result.confidence <= 0.1
        assert "فشل توليد التقرير" in result.notes

    async def test_disabled_llm_never_fabricates_analysis(self, connectors):
        agent = SpecialistAgent(AgentId.FLOW, FakeLLM(enabled=False))
        result = await agent.run("الذهب")
        assert "وضع منقطع" in result.headline
        assert result.signals == []

    async def test_quick_depth_skips_web_research(self, connectors):
        fake = FakeLLM()
        agent = SpecialistAgent(AgentId.FLOW, fake)
        await agent.run("الذهب", depth="quick")
        assert fake.research_calls == []

    async def test_prompt_lists_blind_sources_explicitly(self, connectors):
        connectors["results"] = [ok_connector(), dead_connector("social:x", "لا مفتاح")]
        fake = FakeLLM()
        agent = SpecialistAgent(AgentId.SOCIAL, fake)
        await agent.run("الذهب")
        _, prompt = fake.structure_calls[0]
        assert "social:x" in prompt and "أعمى" in prompt

    async def test_report_is_written_to_memory(self, connectors):
        class Memo:
            def __init__(self): self.rows = []
            def upsert(self, **kw): self.rows.append(kw)
            def search(self, *a, **kw): return []
            def recent(self, *a, **kw): return []

        memo = Memo()
        agent = SpecialistAgent(AgentId.FLOW, FakeLLM(), memory=memo)
        await agent.run("الذهب")
        assert len(memo.rows) == 1 and memo.rows[0]["agent_id"] == "the_trader"


class TestChiefAgent:
    async def test_computed_numbers_override_model_numbers(self):
        """النموذج قد يقترح ثقة 0.70؛ المحرك الحتمي هو من يحسم."""
        draft = default_decision_draft(confidence=0.99, risk_score=0.01)
        reports = [report(AgentId.FLOW, confidence=0.4), report(AgentId.MACRO, confidence=0.5)]
        decision = await ChiefAgent(FakeLLM(decision=draft)).synthesize("الذهب", reports)
        assert decision.confidence != 0.99
        assert decision.risk_score != 0.01

    async def test_detected_conflict_survives_model_silence(self):
        """التضارب المكتشف آلياً لا يمكن للنموذج إخفاؤه."""
        reports = [
            report(AgentId.FLOW, signals=[signal(direction=Direction.BULLISH)]),
            report(AgentId.GEO, signals=[signal(direction=Direction.BEARISH)]),
        ]
        decision = await ChiefAgent(FakeLLM(decision=default_decision_draft(conflicts=[]))) \
            .synthesize("الذهب", reports)
        assert len(decision.conflicts) == 1
        assert "غير محسوم" in decision.conflicts[0].resolution

    async def test_degraded_agent_caps_final_confidence(self):
        reports = [report(AgentId.FLOW, confidence=0.9),
                   report(AgentId.MACRO, confidence=0.9, degraded=True)]
        decision = await ChiefAgent(FakeLLM()).synthesize("الذهب", reports)
        assert decision.confidence <= 0.60
        assert any("بلا مصادر حية" in flag for flag in decision.quality_flags)

    async def test_confidence_trace_is_exposed_to_user(self):
        decision = await ChiefAgent(FakeLLM()).synthesize("الذهب", [report()])
        assert any("سلسلة حساب الثقة" in flag for flag in decision.quality_flags)

    async def test_prompt_contains_every_agent_report(self):
        fake = FakeLLM()
        reports = [report(AgentId.FLOW), report(AgentId.SOCIAL), report(AgentId.MACRO)]
        await ChiefAgent(fake).synthesize("الذهب", reports)
        _, prompt = fake.structure_calls[0]
        for agent in ("the_trader", "abu_aloloum", "economic_analyst"):
            assert agent in prompt

    async def test_chief_has_no_data_connectors(self):
        """الوكيل التنسيقي مُركِّب لا مصدر: لا موصلات مسجّلة له."""
        from backend.tools.registry import CONNECTORS
        assert AgentId.CHIEF not in CONNECTORS

    async def test_offline_chief_refuses_to_decide(self):
        decision = await ChiefAgent(FakeLLM(enabled=False)).synthesize("الذهب", [report()])
        assert "لا قرار" in decision.recommendation
        assert decision.confidence <= 0.2

    async def test_sources_are_deduplicated_across_reports(self):
        reports = [report(AgentId.FLOW), report(AgentId.MACRO)]   # نفس الرابط
        decision = await ChiefAgent(FakeLLM()).synthesize("الذهب", reports)
        assert len(decision.sources_used) == 1

    async def test_failed_synthesis_also_zeroes_confidence(self):
        """فشل النموذج أثناء التركيب لا يُخفى خلف ثقة محسوبة من التقارير."""
        reports = [report(AgentId.FLOW, confidence=0.9), report(AgentId.MACRO, confidence=0.9)]
        decision = await ChiefAgent(FakeLLM(fail_structure=True)).synthesize("الذهب", reports)
        assert decision.confidence <= 0.10
        assert any("لم يُركَّب القرار" in flag for flag in decision.quality_flags)


class TestSourceDegradation:
    """التمييز بين نقص التغطية والعمى الكامل — أهم ما يغيّر ثقة القرار."""

    async def test_missing_key_alone_does_not_degrade_the_report(self, connectors):
        from backend.tools.base import ConnectorResult, FailureKind

        connectors["results"] = [
            ok_connector("news:geo"),
            ConnectorResult.failed("social:x", "X_BEARER_TOKEN غير مضبوط",
                                   FailureKind.MISSING_KEY),
        ]
        agent = SpecialistAgent(AgentId.SOCIAL, FakeLLM())
        result = await agent.run("الذهب")
        assert result.degraded is False            # مصدر حي واحد يكفي للرؤية
        assert result.confidence > 0.25

    async def test_missing_key_is_still_declared_as_a_gap(self, connectors):
        from backend.tools.base import ConnectorResult, FailureKind

        connectors["results"] = [
            ok_connector("news:geo"),
            ConnectorResult.failed("social:x", "X_BEARER_TOKEN غير مضبوط",
                                   FailureKind.MISSING_KEY),
        ]
        agent = SpecialistAgent(AgentId.SOCIAL, FakeLLM())
        result = await agent.run("الذهب")
        assert any("مفتاح غير مضبوط" in gap for gap in result.data_gaps)

    async def test_gap_text_names_the_failure_kind(self, connectors):
        from backend.tools.base import ConnectorResult, FailureKind

        connectors["results"] = [
            ConnectorResult.failed("news:geo", "403", FailureKind.BLOCKED)
        ]
        agent = SpecialistAgent(AgentId.GEO, FakeLLM(research_evidence=[]))
        result = await agent.run("الذهب")
        assert any("وصول محجوب" in gap for gap in result.data_gaps)

    async def test_coverage_summary_reaches_the_notes(self, connectors):
        from backend.tools.base import ConnectorResult, FailureKind

        connectors["results"] = [
            ok_connector("news:geo"),
            ConnectorResult.failed("social:x", "لا مفتاح", FailureKind.MISSING_KEY),
        ]
        agent = SpecialistAgent(AgentId.SOCIAL, FakeLLM())
        result = await agent.run("الذهب")
        assert "تغطية المصادر 1/2" in result.notes
        assert "بانتظار مفاتيح: social:x" in result.notes
