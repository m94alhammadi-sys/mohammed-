"""اختبارات طبقة الخدمة والبوت — بنواة ذكاء وهمية."""

import pytest

from advisor import service as service_mod
from advisor.brain import AdvisorReply
from advisor.market_data import MarketSnapshot, Quote
from advisor.service import AdvisorService
from advisor.storage import Storage
from bots.telegram_bot import _chunks


class StubBrain:
    """يسجّل النص المُرسل للنموذج بدل استدعاء Claude."""

    def __init__(self, text="تحليل تجريبي"):
        self.turns = []
        self.histories = []
        self._text = text

    async def ask(self, user_turn, history=None, **kwargs):
        self.turns.append(user_turn)
        self.histories.append(history or [])
        return AdvisorReply(text=self._text)


@pytest.fixture
async def svc(tmp_path, monkeypatch):
    async def fake_snapshot(include_uae=True):
        snap = MarketSnapshot(taken_at="2026-09-20 10:00 UTC")
        snap.groups["الذهب والسلع"] = [Quote("الذهب", "XAUUSD", 2457.0, 1.5)]
        return snap

    monkeypatch.setattr(service_mod.market_data, "fetch_snapshot", fake_snapshot)
    storage = Storage(str(tmp_path / "s.sqlite3"))
    brain = StubBrain()
    yield AdvisorService(storage, brain), storage, brain
    await storage.close()


async def test_chat_injects_profile_market_and_portfolio(svc):
    service, storage, brain = svc
    profile = await storage.ensure_user(5, "محمد")
    await storage.update_profile(5, risk_profile="محافظ", capital_note="بدون رافعة")
    await storage.add_watch(5, "BTC")
    await storage.upsert_holding(5, "XAUUSD", 3, 2300)
    profile = await storage.get_profile(5)

    await service.chat(profile, "أشتري ذهب الحين؟")

    turn = brain.turns[0]
    assert "محافظ" in turn and "بدون رافعة" in turn
    assert "قائمة المتابعة: BTC" in turn
    assert "XAUUSD: الكمية 3.0" in turn
    assert "الذهب (XAUUSD): 2,457.00" in turn
    assert turn.rstrip().endswith("أشتري ذهب الحين؟")


async def test_chat_persists_both_sides_of_conversation(svc):
    service, storage, _ = svc
    profile = await storage.ensure_user(5)
    await service.chat(profile, "سؤال ١")
    await service.chat(profile, "سؤال ٢")
    history = await storage.recent_messages(5, 10)
    assert [m["role"] for m in history] == ["user", "assistant", "user", "assistant"]
    assert history[0]["content"] == "سؤال ١"


async def test_second_chat_receives_previous_history(svc):
    service, storage, brain = svc
    profile = await storage.ensure_user(5)
    await service.chat(profile, "سؤال ١")
    await service.chat(profile, "سؤال ٢")
    assert brain.histories[0] == []
    assert brain.histories[1][0]["content"] == "سؤال ١"


async def test_portfolio_review_guides_empty_portfolio_without_calling_model(svc):
    service, storage, brain = svc
    profile = await storage.ensure_user(9)
    reply = await service.portfolio_review(profile)
    assert "/add" in reply.text
    assert brain.turns == []          # لم يُستهلك رصيد على محفظة فاضية


async def test_market_block_degrades_when_sources_fail(tmp_path, monkeypatch):
    async def boom(include_uae=True):
        raise RuntimeError("blocked")

    monkeypatch.setattr(service_mod.market_data, "fetch_snapshot", boom)
    storage = Storage(str(tmp_path / "x.sqlite3"))
    brain = StubBrain()
    service = AdvisorService(storage, brain)
    profile = await storage.ensure_user(1)

    await service.chat(profile, "؟")            # لا يرمي استثناء

    assert "اعتمد على البحث في الإنترنت" in brain.turns[0]
    await storage.close()


async def test_analyze_symbol_uses_live_price_when_available(svc, monkeypatch):
    service, storage, brain = svc

    async def fake_symbols(symbols):
        return [Quote("بيتكوين", "BTC", 61000.0, -2.0)], []

    monkeypatch.setattr(service_mod.market_data, "fetch_symbols", fake_symbols)
    profile = await storage.ensure_user(3)
    await service.analyze_symbol(profile, "BTC")
    assert "سعر محدّث من مصدر مباشر" in brain.turns[0]


async def test_analyze_symbol_tells_model_to_search_when_price_missing(svc, monkeypatch):
    service, storage, brain = svc

    async def fake_symbols(symbols):
        return [], ["ADNOC"]

    monkeypatch.setattr(service_mod.market_data, "fetch_symbols", fake_symbols)
    profile = await storage.ensure_user(3)
    await service.analyze_symbol(profile, "ADNOC")
    assert "ابحث في الإنترنت عن السعر الحالي" in brain.turns[0]


# ── تقسيم الرسائل الطويلة لتيليجرام ───────────────────────────
def test_short_text_is_not_split():
    assert _chunks("مرحبا") == ["مرحبا"]


def test_long_text_split_respects_limit_and_keeps_content():
    text = "\n".join(f"سطر رقم {i} فيه كلام كافٍ ليطول النص" for i in range(400))
    parts = _chunks(text)
    assert len(parts) > 1
    assert all(len(p) <= 4000 for p in parts)
    assert "".join(p.replace("\n", "") for p in parts) == text.replace("\n", "")


def test_split_without_newlines_still_terminates():
    parts = _chunks("ا" * 9000)
    assert len(parts) == 3 and all(len(p) <= 4000 for p in parts)


# ── الدالة المشتركة للتقسيم ───────────────────────────────────
def test_split_message_without_separators_terminates():
    from advisor.text import split_message

    parts = split_message("ا" * 9000, 3800)
    assert len(parts) == 3 and all(len(p) <= 3800 for p in parts)


def test_split_message_rejects_bad_limit():
    import pytest as _pytest

    from advisor.text import split_message

    with _pytest.raises(ValueError):
        split_message("نص", 0)
