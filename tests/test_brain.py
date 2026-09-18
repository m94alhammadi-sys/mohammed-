"""اختبارات حلقة الأدوات — بمحاكاة استجابات النموذج بدل استدعائه فعلياً."""

import pytest

from app import brain, db


class Block:
    """بلوك محتوى مزيّف يشبه ما يعيده SDK."""

    def __init__(self, type, **kwargs):
        self.type = type
        self.text = kwargs.get("text", "")
        self.id = kwargs.get("id")
        self.name = kwargs.get("name")
        self.input = kwargs.get("input")

    def model_dump(self, exclude_none=False):
        data = {"type": self.type}
        for key in ("text", "id", "name", "input"):
            value = getattr(self, key)
            if value or not exclude_none:
                data[key] = value
        return data


class Reply:
    def __init__(self, content, stop_reason="end_turn", stop_details=None):
        self.content = content
        self.stop_reason = stop_reason
        self.stop_details = stop_details


@pytest.fixture
def fake_model(monkeypatch):
    """يستبدل نداء النموذج بقائمة ردود محضّرة، ويسجّل الطلبات."""
    calls = []

    def make(replies):
        queue = list(replies)

        def _create(**kwargs):
            # نسخة من قائمة الرسائل لأن الحلقة تعدّلها في مكانها
            calls.append({**kwargs, "messages": list(kwargs["messages"])})
            return queue.pop(0)

        monkeypatch.setattr(brain, "_create", _create)
        return calls

    return make


def test_plain_answer_without_tools(clean_db, phone, fake_model):
    fake_model([Reply([Block("text", text="الذهب في اتجاه صاعد.")])])
    assert brain.respond(phone, "وش رايك في الذهب؟") == "الذهب في اتجاه صاعد."


def test_tool_call_then_answer(clean_db, phone, fake_model):
    calls = fake_model([
        Reply(
            [Block("tool_use", id="t1", name="position_size",
                   input={"capital": 100000, "risk_percent": 1, "entry": 100, "stop_loss": 95})],
            stop_reason="tool_use",
        ),
        Reply([Block("text", text="حجم المركز 200 سهم.")]),
    ])
    assert brain.respond(phone, "احسب لي حجم المركز") == "حجم المركز 200 سهم."
    assert len(calls) == 2

    # نتيجة الأداة وصلت للنموذج في الدورة الثانية
    tool_results = calls[1]["messages"][-1]["content"]
    assert tool_results[0]["type"] == "tool_result"
    assert tool_results[0]["tool_use_id"] == "t1"
    assert "عدد_الوحدات" in tool_results[0]["content"]


def test_parallel_tool_calls_return_in_one_message(clean_db, phone, fake_model):
    calls = fake_model([
        Reply(
            [
                Block("tool_use", id="a", name="search_symbols", input={"query": "ادنوك"}),
                Block("tool_use", id="b", name="manage_watchlist", input={"action": "show"}),
            ],
            stop_reason="tool_use",
        ),
        Reply([Block("text", text="تم.")]),
    ])
    brain.respond(phone, "ابحث وأظهر القائمة")

    results = calls[1]["messages"][-1]["content"]
    assert len(results) == 2
    assert {r["tool_use_id"] for r in results} == {"a", "b"}


def test_failing_tool_returns_error_not_crash(clean_db, phone, fake_model):
    calls = fake_model([
        Reply([Block("tool_use", id="t1", name="position_size", input={"capital": "نص"})],
              stop_reason="tool_use"),
        Reply([Block("text", text="المدخلات غير صحيحة.")]),
    ])
    assert brain.respond(phone, "احسب") == "المدخلات غير صحيحة."
    assert "خطأ" in calls[1]["messages"][-1]["content"][0]["content"]


def test_pause_turn_is_resumed(clean_db, phone, fake_model):
    """أداة البحث في الإنترنت قد توقف الدور مؤقتاً — يجب أن نكمل لا أن نتوقف."""
    calls = fake_model([
        Reply([Block("text", text="أبحث…")], stop_reason="pause_turn"),
        Reply([Block("text", text="النتيجة النهائية.")]),
    ])
    assert brain.respond(phone, "ابحث لي") == "النتيجة النهائية."
    assert len(calls) == 2


def test_refusal_returns_friendly_message(clean_db, phone, fake_model):
    fake_model([Reply([], stop_reason="refusal", stop_details={"category": "x"})])
    assert "ما أقدر أجاوب" in brain.respond(phone, "طلب مرفوض")


def test_empty_response_is_handled(clean_db, phone, fake_model):
    fake_model([Reply([], stop_reason="end_turn")])
    assert "خلل" in brain.respond(phone, "مرحبا")


def test_iteration_cap_stops_infinite_tool_loop(clean_db, phone, fake_model, monkeypatch):
    monkeypatch.setattr(brain, "MAX_ITERATIONS", 3)
    fake_model([
        Reply([Block("tool_use", id=f"t{i}", name="manage_watchlist", input={"action": "show"})],
              stop_reason="tool_use")
        for i in range(3)
    ])
    assert "جزّئ السؤال" in brain.respond(phone, "لف ودور")


def test_conversation_history_is_persisted(clean_db, phone, fake_model):
    fake_model([Reply([Block("text", text="أهلاً بك.")])])
    brain.respond(phone, "السلام عليكم")

    history = db.load_history(phone)
    assert history[0]["role"] == "user"
    assert history[0]["content"][0]["text"] == "السلام عليكم"
    assert history[-1]["role"] == "assistant"


def test_second_turn_includes_previous_context(clean_db, phone, fake_model):
    fake_model([Reply([Block("text", text="رد أول.")]), Reply([Block("text", text="رد ثانٍ.")])])
    brain.respond(phone, "سؤال أول")
    brain.respond(phone, "سؤال ثانٍ")

    history = db.load_history(phone)
    texts = [b.get("text") for m in history for b in m["content"] if isinstance(b, dict)]
    assert "سؤال أول" in texts and "سؤال ثانٍ" in texts


def test_system_prompt_is_cached_and_context_is_dynamic(clean_db, phone, fake_model):
    calls = fake_model([Reply([Block("text", text="ok")])])
    brain.respond(phone, "مرحبا", user_name="محمد")

    system = calls[0]["system"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}      # الجزء الثابت مخزّن
    assert "cache_control" not in system[1]                          # السياق المتغير لا
    assert "محمد" in system[1]["text"]


def test_watchlist_appears_in_context(clean_db, phone, fake_model):
    db.add_watch(phone, "EMAAR.DU", "إعمار العقارية")
    calls = fake_model([Reply([Block("text", text="ok")])])
    brain.respond(phone, "مرحبا")
    assert "EMAAR.DU" in calls[0]["system"][1]["text"]


def test_request_uses_configured_model_and_tools(clean_db, phone, fake_model):
    calls = fake_model([Reply([Block("text", text="ok")])])
    brain.respond(phone, "مرحبا")

    request = calls[0]
    assert request["thinking"] == {"type": "adaptive"}
    assert "effort" in request["output_config"]
    tool_names = {t.get("name") for t in request["tools"]}
    assert "technical_analysis" in tool_names
    assert "web_search" in tool_names          # البحث في الإنترنت مفعّل


def test_run_task_uses_same_loop(clean_db, phone, fake_model):
    fake_model([Reply([Block("text", text="*موجز الصباح*")])])
    assert brain.run_task(phone, "اكتب الموجز") == "*موجز الصباح*"
