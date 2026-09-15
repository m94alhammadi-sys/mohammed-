"""بدائل اختبار: نموذج لغوي وهمي وموصلات بيانات مُتحكَّم بها."""
from __future__ import annotations

from backend.llm import LLMError, ResearchResult
from backend.schemas import (
    DecisionDraft, Direction, Evidence, Horizon, LinkageDraft, OptionDraft,
    ReportDraft, SignalDraft,
)
from backend.tools.base import ConnectorResult


def default_report_draft(**overrides) -> ReportDraft:
    data = dict(
        headline="عنوان اختباري",
        summary="ملخص اختباري",
        signals=[SignalDraft(
            name="إشارة", direction=Direction.BULLISH, strength=0.7,
            horizon=Horizon.SHORT, asset_classes=["الذهب"],
            rationale="سبب", evidence_refs=[0],
        )],
        risks=["خطر"], data_gaps=[], unverified_claims=[],
        confidence=0.75, urgency=0.1, notes="",
    )
    data.update(overrides)
    return ReportDraft(**data)


def default_decision_draft(**overrides) -> DecisionDraft:
    data = dict(
        situation="الموقف",
        linkages=[LinkageDraft(cause="سبب", effect="أثر", channel="سيولة",
                               agents_involved=["the_trader"], strength=0.6)],
        conflicts=[],
        recommendation="التوصية",
        stance=Direction.BULLISH, confidence=0.7, risk_score=0.4,
        options=[OptionDraft(label="انتظار", action="لا فعل", rationale="سبب",
                             risk_level="low", expected_impact="—", invalidation="—")],
        invalidation_triggers=["شرط"], watchlist=["مراقبة"],
    )
    data.update(overrides)
    return DecisionDraft(**data)


class FakeLLM:
    """نموذج وهمي يسجّل ما استُدعي به ويعيد مخرجات محددة مسبقاً."""

    def __init__(self, *, enabled=True, report=None, decision=None,
                 research_evidence=None, fail_structure=False, fail_research=False):
        self.enabled = enabled
        self._report = report or default_report_draft()
        self._decision = decision or default_decision_draft()
        self._research_evidence = research_evidence or []
        self._fail_structure = fail_structure
        self._fail_research = fail_research
        self.research_calls: list[tuple[str, str]] = []
        self.structure_calls: list[tuple[str, str]] = []
        self.chat_calls: list[list[dict]] = []

    async def research(self, system, prompt, **kwargs) -> ResearchResult:
        self.research_calls.append((system, prompt))
        if self._fail_research:
            return ResearchResult(text="فشل البحث", degraded=True)
        return ResearchResult(
            text="نص بحث", evidence=list(self._research_evidence),
            used_web=bool(self._research_evidence),
        )

    async def structure(self, system, prompt, schema_cls, **kwargs):
        self.structure_calls.append((system, prompt))
        if self._fail_structure:
            raise LLMError("فشل متعمّد")
        return self._decision if schema_cls is DecisionDraft else self._report

    async def chat(self, system, history, **kwargs) -> str:
        self.chat_calls.append(history)
        return "رد وهمي"


def ok_connector(name="fake", count=2) -> ConnectorResult:
    return ConnectorResult(
        name=name, ok=True, note="ok",
        evidence=[
            Evidence(source_type="news", title=f"خبر {i}",
                     url=f"https://example.com/{i}", reliability=0.8)
            for i in range(count)
        ],
    )


def dead_connector(name="fake", reason="محجوب") -> ConnectorResult:
    return ConnectorResult.failed(name, reason)
