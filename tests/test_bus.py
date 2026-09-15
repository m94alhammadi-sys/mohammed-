"""اختبارات ناقل الوكلاء."""
import asyncio

import pytest

from backend.bus import MessageBus
from backend.schemas import AgentId, Envelope, MessageType

pytestmark = pytest.mark.asyncio


def envelope(sender, recipients, correlation="cyc_1", mtype=MessageType.REPORT):
    return Envelope(correlation_id=correlation, sender=sender,
                    recipients=recipients, type=mtype, topic="الذهب")


async def test_direct_delivery():
    bus = MessageBus()
    bus.register(AgentId.CHIEF)
    await bus.publish(envelope(AgentId.FLOW, [AgentId.CHIEF]))
    received = await asyncio.wait_for(bus.receive(AgentId.CHIEF), timeout=1)
    assert received.sender is AgentId.FLOW


async def test_broadcast_reaches_everyone_but_sender():
    bus = MessageBus()
    for agent in (AgentId.CHIEF, AgentId.FLOW, AgentId.SOCIAL):
        bus.register(agent)
    await bus.publish(envelope(AgentId.FLOW, [], mtype=MessageType.ALERT))

    assert (await asyncio.wait_for(bus.receive(AgentId.CHIEF), 1)).type is MessageType.ALERT
    assert (await asyncio.wait_for(bus.receive(AgentId.SOCIAL), 1)).type is MessageType.ALERT
    assert bus.register(AgentId.FLOW).empty()          # المرسِل لا يستقبل رسالته


async def test_collect_returns_when_expected_count_reached():
    bus = MessageBus()
    bus.register(AgentId.CHIEF)
    for sender in (AgentId.FLOW, AgentId.MACRO, AgentId.GEO):
        await bus.publish(envelope(sender, [AgentId.CHIEF]))

    collected = await bus.collect(AgentId.CHIEF, "cyc_1", expected=3, timeout=1)
    assert len(collected) == 3


async def test_collect_returns_partial_on_timeout():
    bus = MessageBus()
    bus.register(AgentId.CHIEF)
    await bus.publish(envelope(AgentId.FLOW, [AgentId.CHIEF]))

    collected = await bus.collect(AgentId.CHIEF, "cyc_1", expected=5, timeout=0.2)
    assert len(collected) == 1                        # لا يعلّق في انتظار الغائبين


async def test_collect_ignores_other_cycles():
    bus = MessageBus()
    bus.register(AgentId.CHIEF)
    await bus.publish(envelope(AgentId.FLOW, [AgentId.CHIEF], correlation="cyc_other"))

    collected = await bus.collect(AgentId.CHIEF, "cyc_1", expected=1, timeout=0.2)
    assert collected == []


async def test_observer_sees_all_traffic():
    bus = MessageBus()
    bus.register(AgentId.CHIEF)
    seen = []
    bus.observe(lambda env: asyncio.sleep(0, result=seen.append(env)))

    await bus.publish(envelope(AgentId.FLOW, [AgentId.CHIEF]))
    await asyncio.sleep(0.05)
    assert len(seen) == 1


async def test_audit_trail_filters_by_correlation():
    bus = MessageBus()
    bus.register(AgentId.CHIEF)
    await bus.publish(envelope(AgentId.FLOW, [AgentId.CHIEF], correlation="a"))
    await bus.publish(envelope(AgentId.GEO, [AgentId.CHIEF], correlation="b"))

    assert len(bus.audit_trail("a")) == 1
    assert len(bus.audit_trail()) == 2


async def test_failing_handler_does_not_break_the_bus():
    bus = MessageBus()
    bus.register(AgentId.CHIEF)

    async def broken(_env):
        raise RuntimeError("انفجار متعمّد")

    bus.subscribe(AgentId.CHIEF, broken)
    await bus.publish(envelope(AgentId.FLOW, [AgentId.CHIEF]))
    await asyncio.sleep(0.05)
    assert len(bus.audit_trail()) == 1                # الرسالة سُجّلت رغم فشل المعالج
