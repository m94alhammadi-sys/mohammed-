"""اختبارات برومبتات النظام — الحدود المكتوبة هي جزء من المنتج لا زينة."""
import re

import pytest

from backend.prompts import AGENT_PROMPTS, SHARED_CORE, system_prompt_for
from backend.schemas import AgentId

SPECIALISTS = list(AGENT_PROMPTS)


def flat(agent_id: AgentId) -> str:
    """نص البرومبت بمسافات موحّدة — البرومبتات ملفوفة على ٧٩ عموداً."""
    return re.sub(r"\s+", " ", system_prompt_for(agent_id))


@pytest.mark.parametrize("agent_id", SPECIALISTS)
def test_every_specialist_inherits_the_shared_core(agent_id):
    assert SHARED_CORE in system_prompt_for(agent_id)


@pytest.mark.parametrize("agent_id", SPECIALISTS)
def test_every_specialist_has_an_explicit_do_not_section(agent_id):
    assert "ما لا تفعله أبداً" in flat(agent_id)


@pytest.mark.parametrize("agent_id", SPECIALISTS)
def test_every_specialist_has_a_methodological_warning(agent_id):
    assert "تحذير منهجي إلزامي" in flat(agent_id)


@pytest.mark.parametrize("agent_id", SPECIALISTS)
def test_specialists_are_barred_from_recommending(agent_id):
    """التوصية حكر على الوكيل التنسيقي — يجب أن يُنص عليها في كل برومبت."""
    assert "الوكيل التنسيقي" in flat(agent_id)


def test_chief_prompt_demands_invalidation_triggers():
    prompt = flat(AgentId.CHIEF)
    assert "شروط الإبطال" in prompt and "غير قابلة للمساءلة" in prompt


def test_chief_prompt_forbids_averaging_confidence():
    assert "ليست متوسط ثقة الوكلاء" in flat(AgentId.CHIEF)


def test_chief_prompt_caps_confidence_on_degraded_agents():
    assert "0.60" in flat(AgentId.CHIEF)


def test_chief_is_forbidden_from_adding_its_own_information():
    assert "مُركِّب لا مصدر" in flat(AgentId.CHIEF)


def test_confidence_ladder_is_numeric_not_vague():
    """سلّم الثقة بأرقام صريحة يمنع «غالباً» و«ربما»."""
    for bound in ("0.85", "0.60", "0.35"):
        assert bound in SHARED_CORE


def test_unknown_agent_raises():
    with pytest.raises(KeyError):
        system_prompt_for(AgentId.USER)
