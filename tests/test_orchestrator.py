"""اختبارات المنسّق: التوزيع، الالتقاء، وتحمّل أعطال الوكلاء."""
import asyncio

import pytest

from backend.bus import MessageBus
from backend.config import Settings
from backend.orchestrator import SPECIALISTS, Orchestrator
from backend.schemas import AgentId, MessageType
from tests.fakes import FakeLLM, default_report_draft, ok_connector

pytestmark = pytest.mark.asyncio


@pytest.fixture
def no_network(monkeypatch):
    async def fake_gather(agent_id, topic):
        return [ok_connector()]

    monkeypatch.setattr("backend.agents.base.gather_context", fake_gather)


@pytest.fixture
def orch(no_network):
    return Orchestrator(llm=FakeLLM(), message_bus=MessageBus())


async def test_all_specialists_report(orch):
    decision, reports = await orch.run_cycle("الذهب")
    assert len(reports) == len(SPECIALISTS)
    assert {r.agent_id for r in reports} == set(SPECIALISTS)
    assert decision.topic == "الذهب"


async def test_agents_run_in_parallel_not_in_sequence(no_network, monkeypatch):
    """خمسة وكلاء بزمن ٠٫٢ ثانية لكل منهم يجب أن ينتهوا في أقل من ٠٫٥ لا في ١٫٠."""
    from backend.agents.base import SpecialistAgent
    from tests.factories import report as make_report

    async def slow_run(self, topic, depth="standard"):
        await asyncio.sleep(0.2)
        return make_report(self.agent_id)

    monkeypatch.setattr(SpecialistAgent, "run", slow_run)
    orch = Orchestrator(llm=FakeLLM(), message_bus=MessageBus())

    started = asyncio.get_running_loop().time()
    await orch.run_cycle("الذهب")
    assert asyncio.get_running_loop().time() - started < 0.6


async def test_subset_of_agents_can_be_selected(orch):
    _, reports = await orch.run_cycle("الذهب", agents=[AgentId.FLOW, AgentId.MACRO])
    assert {r.agent_id for r in reports} == {AgentId.FLOW, AgentId.MACRO}


async def test_failing_agent_becomes_declared_gap_not_silent_absence(no_network, monkeypatch):
    from backend.agents.base import SpecialistAgent
    from tests.factories import report as make_report

    async def maybe_fail(self, topic, depth="standard"):
        if self.agent_id is AgentId.SOCIAL:
            raise RuntimeError("انهيار متعمّد")
        return make_report(self.agent_id)

    monkeypatch.setattr(SpecialistAgent, "run", maybe_fail)
    orch = Orchestrator(llm=FakeLLM(), message_bus=MessageBus())

    decision, reports = await orch.run_cycle("الذهب")
    social = next(r for r in reports if r.agent_id is AgentId.SOCIAL)
    assert social.degraded and "تعذّر" in social.headline
    assert decision.confidence <= 0.60          # الغياب يخفض الثقة تلقائياً


async def test_timeout_is_contained_to_one_agent(no_network, monkeypatch):
    from backend.agents.base import SpecialistAgent
    from tests.factories import report as make_report

    async def maybe_hang(self, topic, depth="standard"):
        if self.agent_id is AgentId.GEO:
            await asyncio.sleep(5)
        return make_report(self.agent_id)

    monkeypatch.setattr(SpecialistAgent, "run", maybe_hang)
    cfg = Settings(agent_timeout_s=1)
    orch = Orchestrator(llm=FakeLLM(), message_bus=MessageBus(), cfg=cfg)

    decision, reports = await orch.run_cycle("الذهب")
    assert len(reports) == len(SPECIALISTS)
    assert next(r for r in reports if r.agent_id is AgentId.GEO).degraded


async def test_every_message_shares_one_correlation_id(orch):
    await orch.run_cycle("الذهب", correlation_id="cyc_test")
    trail = orch.bus.audit_trail("cyc_test")
    assert len(trail) >= len(SPECIALISTS) + 2      # مهمة + تقارير + قرار
    assert all(env.correlation_id == "cyc_test" for env in trail)


async def test_reports_are_addressed_to_the_chief(orch):
    await orch.run_cycle("الذهب", correlation_id="cyc_addr")
    reports = [e for e in orch.bus.audit_trail("cyc_addr") if e.type is MessageType.REPORT]
    assert reports and all(e.recipients == [AgentId.CHIEF] for e in reports)


async def test_decision_is_addressed_to_the_user(orch):
    await orch.run_cycle("الذهب", correlation_id="cyc_dec")
    decisions = [e for e in orch.bus.audit_trail("cyc_dec") if e.type is MessageType.DECISION]
    assert len(decisions) == 1 and decisions[0].recipients == [AgentId.USER]


async def test_urgent_breaking_event_is_broadcast(no_network):
    urgent = default_report_draft(urgency=0.95)
    orch = Orchestrator(llm=FakeLLM(report=urgent), message_bus=MessageBus())
    await orch.run_cycle("زلزال", correlation_id="cyc_alert")
    alerts = [e for e in orch.bus.audit_trail("cyc_alert") if e.type is MessageType.ALERT]
    assert len(alerts) == 1
    assert alerts[0].sender is AgentId.BREAKING and alerts[0].is_broadcast()


async def test_calm_breaking_event_is_not_broadcast(no_network):
    calm = default_report_draft(urgency=0.2)
    orch = Orchestrator(llm=FakeLLM(report=calm), message_bus=MessageBus())
    await orch.run_cycle("خبر عادي", correlation_id="cyc_calm")
    assert not [e for e in orch.bus.audit_trail("cyc_calm") if e.type is MessageType.ALERT]


async def test_status_hook_reports_lifecycle(orch):
    events = []

    async def hook(agent_id, state, meta):
        events.append((agent_id, state))

    await orch.run_cycle("الذهب", status=hook)
    states = {state for _, state in events}
    assert {"working", "reported", "synthesizing", "done"} <= states


async def test_direct_chat_stays_with_one_agent(orch):
    reply = await orch.ask_agent(AgentId.FLOW, [{"role": "user", "content": "مرحباً"}])
    assert reply == "رد وهمي"
    assert len(orch.llm.chat_calls) == 1
