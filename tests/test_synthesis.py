"""اختبارات محرك التركيب الحتمي — هذه هي الأرقام التي يُبنى عليها القرار."""
import pytest

from backend.schemas import AgentId, Direction
from backend.synthesis import (
    DEGRADED_CONFIDENCE_CAP, aggregate_confidence, consensus_stance,
    corroboration_index, dedupe_evidence, detect_conflicts, quality_flags, risk_score,
)
from tests.factories import evidence, report, signal


class TestConsensusStance:
    def test_unanimous_bullish(self):
        reports = [report(AgentId.FLOW), report(AgentId.MACRO)]
        result = consensus_stance(reports)
        assert result.direction is Direction.BULLISH
        assert result.score == pytest.approx(1.0)
        assert result.agreement == pytest.approx(1.0)

    def test_opposing_signals_cancel_to_neutral(self):
        reports = [
            report(AgentId.FLOW, signals=[signal(direction=Direction.BULLISH)]),
            report(AgentId.MACRO, signals=[signal(direction=Direction.BEARISH)]),
        ]
        # الوزنان متقاربان (1.00 مقابل 0.95) فالمحصلة قرب الصفر
        assert consensus_stance(reports).direction is Direction.NEUTRAL

    def test_social_alone_is_outweighed_by_flow(self):
        """الضجيج الاجتماعي وحده لا يقلب الاتجاه ضد التدفق الفعلي."""
        reports = [
            report(AgentId.SOCIAL, signals=[signal(direction=Direction.BULLISH)]),
            report(AgentId.FLOW, signals=[signal(direction=Direction.BEARISH)]),
        ]
        assert consensus_stance(reports).direction is Direction.BEARISH

    def test_no_signals_is_neutral(self):
        assert consensus_stance([report(signals=[])]).direction is Direction.NEUTRAL

    def test_empty_reports(self):
        result = consensus_stance([])
        assert result.direction is Direction.NEUTRAL and result.score == 0.0


class TestConflicts:
    def test_opposite_directions_same_asset_conflict(self):
        reports = [
            report(AgentId.FLOW, signals=[signal(direction=Direction.BULLISH, assets=("الذهب",))]),
            report(AgentId.GEO, signals=[signal(direction=Direction.BEARISH, assets=("الذهب",))]),
        ]
        conflicts = detect_conflicts(reports)
        assert len(conflicts) == 1
        assert {conflicts[0].agent_a, conflicts[0].agent_b} == {AgentId.FLOW, AgentId.GEO}

    def test_different_assets_do_not_conflict(self):
        reports = [
            report(AgentId.FLOW, signals=[signal(direction=Direction.BULLISH, assets=("الذهب",))]),
            report(AgentId.GEO, signals=[signal(direction=Direction.BEARISH, assets=("النفط",))]),
        ]
        assert detect_conflicts(reports) == []

    def test_weak_signals_are_ignored(self):
        reports = [
            report(AgentId.FLOW, signals=[signal(direction=Direction.BULLISH, strength=0.2)]),
            report(AgentId.GEO, signals=[signal(direction=Direction.BEARISH, strength=0.2)]),
        ]
        assert detect_conflicts(reports) == []

    def test_same_agent_internal_disagreement_is_not_a_conflict(self):
        reports = [report(AgentId.FLOW, signals=[
            signal(direction=Direction.BULLISH), signal(direction=Direction.BEARISH),
        ])]
        assert detect_conflicts(reports) == []

    def test_severity_scales_with_confidence(self):
        confident = detect_conflicts([
            report(AgentId.FLOW, confidence=0.9, signals=[signal(direction=Direction.BULLISH)]),
            report(AgentId.GEO, confidence=0.9, signals=[signal(direction=Direction.BEARISH)]),
        ])
        hesitant = detect_conflicts([
            report(AgentId.FLOW, confidence=0.4, signals=[signal(direction=Direction.BULLISH)]),
            report(AgentId.GEO, confidence=0.4, signals=[signal(direction=Direction.BEARISH)]),
        ])
        assert confident[0].severity > hesitant[0].severity


class TestConfidence:
    def test_starts_from_weakest_link_not_average(self):
        reports = [report(AgentId.FLOW, confidence=0.9), report(AgentId.MACRO, confidence=0.3)]
        value, reasons = aggregate_confidence(reports, [])
        assert value <= 0.3 + 0.30            # لا يقفز إلى متوسط 0.6
        assert "أضعف حلقة" in reasons[0]

    def test_degraded_agent_caps_confidence(self):
        reports = [
            report(AgentId.FLOW, confidence=0.95),
            report(AgentId.MACRO, confidence=0.95, degraded=True),
        ]
        value, reasons = aggregate_confidence(reports, [])
        assert value <= DEGRADED_CONFIDENCE_CAP
        assert any("سقف" in r for r in reasons)

    def test_conflicts_reduce_confidence(self):
        reports = [
            report(AgentId.FLOW, confidence=0.8, signals=[signal(direction=Direction.BULLISH)]),
            report(AgentId.GEO, confidence=0.8, signals=[signal(direction=Direction.BEARISH)]),
        ]
        clean, _ = aggregate_confidence(reports, [])
        conflicted, _ = aggregate_confidence(reports, detect_conflicts(reports))
        assert conflicted < clean

    def test_data_gaps_reduce_confidence(self):
        base = [report(confidence=0.8)]
        gapped = [report(confidence=0.8, gaps=("فجوة١", "فجوة٢", "فجوة٣"))]
        assert aggregate_confidence(gapped, [])[0] < aggregate_confidence(base, [])[0]

    def test_never_exceeds_ceiling_or_drops_below_floor(self):
        high = [report(AgentId.FLOW, confidence=1.0), report(AgentId.MACRO, confidence=1.0)]
        assert aggregate_confidence(high, [])[0] <= 0.95
        assert aggregate_confidence([], [])[0] >= 0.05

    def test_every_adjustment_is_explained(self):
        reports = [report(AgentId.FLOW, confidence=0.7, gaps=("فجوة",), unverified=("ادعاء",))]
        _, reasons = aggregate_confidence(reports, [])
        assert any("فجوة" in r for r in reasons)
        assert any("غير مؤكد" in r for r in reasons)


class TestRisk:
    def test_urgency_raises_risk(self):
        calm = risk_score([report(urgency=0.0)], [])
        alarm = risk_score([report(AgentId.BREAKING, urgency=0.95)], [])
        assert alarm > calm

    def test_bearish_signals_raise_risk(self):
        bullish = risk_score([report(signals=[signal(direction=Direction.BULLISH)])], [])
        bearish = risk_score([report(signals=[signal(direction=Direction.BEARISH)])], [])
        assert bearish > bullish

    def test_bounded_zero_to_one(self):
        extreme = [report(AgentId.BREAKING, urgency=1.0, risks=tuple("خطر" * 1 for _ in range(30)),
                          signals=[signal(direction=Direction.BEARISH, strength=1.0)])]
        value = risk_score(extreme, detect_conflicts(extreme))
        assert 0.0 <= value <= 1.0


class TestEvidence:
    def test_dedupe_keeps_highest_reliability(self):
        reports = [
            report(AgentId.FLOW, evidence_items=[evidence(url="https://a.com", reliability=0.5)]),
            report(AgentId.MACRO, evidence_items=[evidence(url="https://a.com", reliability=0.9)]),
        ]
        merged = dedupe_evidence(reports)
        assert len(merged) == 1 and merged[0].reliability == 0.9

    def test_corroboration_index_counts_shared_sources(self):
        shared = [
            report(AgentId.FLOW, evidence_items=[evidence(url="https://a.com")]),
            report(AgentId.MACRO, evidence_items=[evidence(url="https://a.com")]),
        ]
        distinct = [
            report(AgentId.FLOW, evidence_items=[evidence(url="https://a.com")]),
            report(AgentId.MACRO, evidence_items=[evidence(url="https://b.com")]),
        ]
        assert corroboration_index(shared) == 1.0
        assert corroboration_index(distinct) == 0.0


class TestQualityFlags:
    def test_flags_degraded_agents(self):
        flags = quality_flags([report(degraded=True)], [])
        assert any("بلا مصادر حية" in f for f in flags)

    def test_flags_sentiment_only_signal(self):
        reports = [
            report(AgentId.SOCIAL, signals=[signal()]),
            report(AgentId.FLOW, signals=[]),
            report(AgentId.MACRO, signals=[]),
        ]
        assert any("ضجيج محتمل" in f for f in quality_flags(reports, []))

    def test_flags_missing_evidence(self):
        flags = quality_flags([report(evidence_items=[])], [])
        assert any("لا توجد أدلة" in f for f in flags)
