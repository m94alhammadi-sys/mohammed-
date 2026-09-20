"""اختبارات نواة الذكاء بعميل Anthropic وهمي — بدون أي اتصال حقيقي."""

from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from advisor import brain as brain_mod
from advisor.brain import AdvisorBrain, AdvisorReply
from advisor.prompts import DISCLAIMER


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def search_result_block(title, url):
    return SimpleNamespace(
        type="web_search_tool_result",
        content=[SimpleNamespace(type="web_search_result", title=title, url=url)],
    )


def fake_message(content, stop_reason="end_turn"):
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=100, output_tokens=50,
                              cache_read_input_tokens=0, cache_creation_input_tokens=0),
    )


class FakeStream:
    def __init__(self, message):
        self._message = message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get_final_message(self):
        return self._message


class FakeMessages:
    """يسجّل كل طلب ويعيد الردود بالترتيب؛ يمكن جعله يرمي خطأ أولاً."""

    def __init__(self, responses, raise_first=None):
        self.responses = list(responses)
        self.raise_first = raise_first
        self.calls = []

    def stream(self, **params):
        self.calls.append(params)
        if self.raise_first is not None:
            err, self.raise_first = self.raise_first, None
            raise err
        return FakeStream(self.responses.pop(0))


class FakeClient:
    def __init__(self, responses, raise_first=None):
        self.messages = FakeMessages(responses)
        self.beta = SimpleNamespace(messages=FakeMessages(responses, raise_first=raise_first))


@pytest.fixture
def make_brain(monkeypatch):
    def factory(responses, raise_first=None):
        client = FakeClient(responses, raise_first=raise_first)
        monkeypatch.setattr(brain_mod.anthropic, "AsyncAnthropic", lambda **kw: client)
        b = AdvisorBrain(api_key="test")
        return b, client
    return factory


async def test_request_shape_has_web_tools_thinking_and_cached_system(make_brain):
    b, client = make_brain([fake_message([text_block("رد")])])
    await b.ask("وش أخبار الذهب؟")

    params = client.beta.messages.calls[0]
    assert params["model"] == "claude-opus-5"
    assert params["thinking"] == {"type": "adaptive"}
    assert params["output_config"]["effort"] in ("low", "medium", "high", "xhigh", "max")
    assert params["system"][0]["cache_control"] == {"type": "ephemeral"}
    tool_types = {t["type"] for t in params["tools"]}
    assert tool_types == {"web_search_20260209", "web_fetch_20260209"}
    assert params["messages"][-1] == {"role": "user", "content": "وش أخبار الذهب؟"}


async def test_history_is_passed_through(make_brain):
    b, client = make_brain([fake_message([text_block("رد")])])
    history = [
        {"role": "user", "content": "سؤال سابق"},
        {"role": "assistant", "content": "جواب سابق"},
        {"role": "system", "content": "يُتجاهل"},
    ]
    await b.ask("السؤال الجديد", history)
    messages = client.beta.messages.calls[0]["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]


async def test_sources_collected_from_web_search(make_brain):
    b, _ = make_brain([fake_message([
        search_result_block("الفيدرالي يثبت الفائدة", "https://www.reuters.com/markets/x"),
        text_block("الخلاصة: ..."),
    ])])
    reply = await b.ask("؟")
    assert reply.searched == 1
    assert reply.sources == ["الفيدرالي يثبت الفائدة (reuters.com)"]
    assert "🔎 مصادر" in reply.formatted()


async def test_pause_turn_is_resumed_and_text_merged(make_brain):
    b, client = make_brain([
        fake_message([text_block("الجزء الأول")], stop_reason="pause_turn"),
        fake_message([text_block("الجزء الثاني")], stop_reason="end_turn"),
    ])
    reply = await b.ask("سؤال طويل")
    assert len(client.beta.messages.calls) == 2
    assert "الجزء الأول" in reply.text and "الجزء الثاني" in reply.text
    # الدور المتوقف يُعاد إرساله كرسالة مساعد حتى يُستأنف
    assert client.beta.messages.calls[1]["messages"][-1]["role"] == "assistant"


async def test_refusal_returns_safe_message(make_brain):
    b, _ = make_brain([fake_message([], stop_reason="refusal")])
    reply = await b.ask("طلب مرفوض")
    assert reply.stop_reason == "refusal"
    assert "تعذّر" in reply.text


async def test_falls_back_to_stable_endpoint_when_beta_unsupported(make_brain):
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.BadRequestError(
        "fallbacks is not supported for this account",
        response=httpx2.Response(400, request=req), body=None,
    )
    b, client = make_brain([fake_message([text_block("رد")])], raise_first=err)
    reply = await b.ask("؟")
    assert reply.text == "رد"
    assert b._use_fallbacks is False            # أُطفئ تلقائياً
    assert len(client.messages.calls) == 1      # استُخدم المسار المستقر
    assert "betas" not in client.messages.calls[0]


async def test_unrelated_bad_request_is_not_swallowed(make_brain):
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.BadRequestError(
        "credit balance is too low", response=httpx2.Response(400, request=req), body=None,
    )
    b, _ = make_brain([fake_message([text_block("رد")])], raise_first=err)
    with pytest.raises(anthropic.BadRequestError):
        await b.ask("؟")


def test_formatted_always_appends_disclaimer_once():
    assert AdvisorReply(text="تحليل").formatted().count(DISCLAIMER) == 1
    assert AdvisorReply(text=f"تحليل\n\n{DISCLAIMER}").formatted().count(DISCLAIMER) == 1


def test_formatted_handles_empty_text():
    assert "لم أتمكن" in AdvisorReply(text="").formatted()


def test_missing_api_key_is_a_clear_error(monkeypatch):
    from dataclasses import replace

    monkeypatch.setattr(brain_mod, "settings", replace(brain_mod.settings, anthropic_api_key=""))
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        AdvisorBrain(api_key="")
