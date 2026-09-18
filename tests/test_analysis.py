"""اختبارات محرك التحليل ودرجة قوة الإشارة."""

import pytest

from app.market.analysis import Signal, _apply_trend_context, _bias_label, _score, analyze_frame
from app.market.data import MarketDataError


def test_uptrend_scores_bullish(uptrend):
    result = analyze_frame("TEST", uptrend)
    assert result.score > 60
    assert "صاعد" in result.bias
    assert result.setup["الاتجاه"] == "شراء"


def test_uptrend_setup_has_valid_risk_structure(uptrend):
    setup = analyze_frame("TEST", uptrend).setup
    assert setup["وقف_الخسارة"] < setup["الدخول_المقترح"]
    assert all(t > setup["الدخول_المقترح"] for t in setup["الأهداف"])
    assert setup["المخاطرة_للعائد"] > 0


def test_downtrend_scores_bearish(downtrend):
    result = analyze_frame("TEST", downtrend)
    assert result.score < 50


def test_short_frame_raises(uptrend):
    with pytest.raises(MarketDataError):
        analyze_frame("TEST", uptrend.tail(10))


def test_warns_on_limited_history(uptrend):
    result = analyze_frame("TEST", uptrend.tail(120))
    assert any("EMA200" in w for w in result.warnings)


def test_score_is_neutral_without_signals():
    assert _score([]) == 50.0


def test_score_symmetry():
    bull = [Signal("أ", "صاعد", 2.0, ""), Signal("ب", "صاعد", 2.0, "")]
    bear = [Signal("أ", "هابط", 2.0, ""), Signal("ب", "هابط", 2.0, "")]
    assert _score(bull) + _score(bear) == pytest.approx(100.0)


def test_score_confidence_scales_with_evidence():
    """إشارة واحدة لا تعطي نفس ثقة خمس إشارات متفقة."""
    one = _score([Signal("أ", "صاعد", 2.0, "")])
    many = _score([Signal(f"إشارة{i}", "صاعد", 2.0, "") for i in range(5)])
    assert 50 < one < many


def test_bias_labels_cover_range():
    assert _bias_label(90) == "صاعد قوي"
    assert _bias_label(65) == "صاعد"
    assert _bias_label(50) == "محايد / عرضي"
    assert _bias_label(30) == "هابط"
    assert _bias_label(10) == "هابط قوي"


def test_counter_trend_signals_downweighted_in_strong_trend():
    """التشبع البيعي وسط هبوط مؤكد ليس إشارة شراء — يجب تخفيض وزنه."""
    signals = [Signal("تشبع بيعي (RSI)", "صاعد", 1.8, "RSI منخفض")]
    adjusted = _apply_trend_context(signals, adx_v=35.0, plus_di=10.0, minus_di=30.0)
    assert adjusted[0].weight < 1.8
    assert "مخفّض" in adjusted[0].detail


def test_trend_context_ignored_when_no_trend():
    signals = [Signal("تشبع بيعي (RSI)", "صاعد", 1.8, "RSI منخفض")]
    adjusted = _apply_trend_context(signals, adx_v=15.0, plus_di=20.0, minus_di=18.0)
    assert adjusted[0].weight == 1.8


def test_analysis_dict_has_arabic_keys(uptrend):
    payload = analyze_frame("TEST", uptrend).to_dict()
    for key in ("الرمز", "السعر", "درجة_القوة", "الانحياز", "المؤشرات", "المستويات", "الإشارات"):
        assert key in payload


def test_levels_bracket_the_price(sideways):
    result = analyze_frame("TEST", sideways)
    assert all(s < result.price for s in result.levels["دعوم"])
    assert all(r > result.price for r in result.levels["مقاومات"])
