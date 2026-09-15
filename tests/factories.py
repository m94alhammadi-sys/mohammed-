"""مصانع بيانات للاختبارات."""
from backend.schemas import AgentId, AgentReport, Direction, Evidence, Horizon, Signal


def evidence(title="خبر", url="https://example.com/1", reliability=0.8, source="news"):
    return Evidence(source_type=source, title=title, url=url, reliability=reliability)


def signal(name="إشارة", direction=Direction.BULLISH, strength=0.8,
           assets=("الذهب",), refs=(0,)):
    return Signal(
        name=name, direction=direction, strength=strength, horizon=Horizon.SHORT,
        asset_classes=list(assets), rationale="سبب", evidence_refs=list(refs),
    )


def report(agent_id=AgentId.FLOW, confidence=0.8, signals=None, evidence_items=None,
           gaps=(), unverified=(), risks=(), urgency=0.0, degraded=False):
    return AgentReport(
        agent_id=agent_id, topic="الذهب", headline="عنوان", summary="ملخص",
        signals=list(signals if signals is not None else [signal()]),
        evidence=list(evidence_items if evidence_items is not None else [evidence()]),
        risks=list(risks), data_gaps=list(gaps), unverified_claims=list(unverified),
        confidence=confidence, urgency=urgency, degraded=degraded,
    )
