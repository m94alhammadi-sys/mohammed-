"""اختبارات الماسح الاستباقي — قرار «متى يستحق الأمر إزعاج المستخدم»."""

import pytest

from app import db, scanner
from app.config import settings
from app.market.analysis import analyze_frame


@pytest.fixture
def captured(monkeypatch):
    """يلتقط الرسائل بدل إرسالها فعلياً لواتساب."""
    sent = []
    monkeypatch.setattr(scanner, "notify", lambda phone, text: sent.append((phone, text)) or True)
    return sent


def test_opportunity_threshold(uptrend, sideways):
    assert scanner._is_opportunity(analyze_frame("T", uptrend)) is True
    assert scanner._is_opportunity(analyze_frame("T", sideways)) is False


def test_signal_kind_uses_strongest_signal(uptrend):
    analysis = analyze_frame("T", uptrend)
    kind = scanner._signal_kind(analysis)
    assert analysis.bias in kind
    assert ":" in kind


def test_model_can_veto_a_weak_signal(plain_phone, captured, monkeypatch, uptrend):
    """لو رد النموذج بـ «تجاهل» لا نرسل شيئاً — لكن نسجّلها لمنع التكرار."""
    db.add_watch(plain_phone, "TEST", "اختبار")
    monkeypatch.setattr(scanner, "analyze", lambda s, **kw: analyze_frame(s, uptrend))
    monkeypatch.setattr(scanner, "run_task", lambda *a, **kw: "تجاهل")

    assert scanner.scan_opportunities() == 0
    assert captured == []
    assert db.alerts_sent_today(plain_phone) == 1          # سُجّلت كمرفوضة


def test_confirmed_signal_is_sent(plain_phone, captured, monkeypatch, uptrend):
    db.add_watch(plain_phone, "TEST", "اختبار")
    monkeypatch.setattr(scanner, "analyze", lambda s, **kw: analyze_frame(s, uptrend))
    monkeypatch.setattr(scanner, "run_task", lambda *a, **kw: "🔔 *فرصة محتملة*\nتفاصيل")

    assert scanner.scan_opportunities() == 1
    assert captured[0][0] == plain_phone
    assert "فرصة محتملة" in captured[0][1]


def test_cooldown_prevents_duplicate_alerts(plain_phone, captured, monkeypatch, uptrend):
    db.add_watch(plain_phone, "TEST", "اختبار")
    monkeypatch.setattr(scanner, "analyze", lambda s, **kw: analyze_frame(s, uptrend))
    monkeypatch.setattr(scanner, "run_task", lambda *a, **kw: "🔔 تنبيه")

    assert scanner.scan_opportunities() == 1
    assert scanner.scan_opportunities() == 0          # نفس الإشارة خلال فترة التهدئة
    assert len(captured) == 1


def test_daily_cap_is_enforced(plain_phone, captured, monkeypatch, uptrend):
    from dataclasses import replace

    monkeypatch.setattr(scanner, "settings", replace(settings, max_alerts_per_day=2))
    for _ in range(2):
        db.record_alert(plain_phone, "X", "سابق", 80.0, {})

    db.add_watch(plain_phone, "TEST", "اختبار")
    monkeypatch.setattr(scanner, "analyze", lambda s, **kw: analyze_frame(s, uptrend))
    monkeypatch.setattr(scanner, "run_task", lambda *a, **kw: "🔔 تنبيه")

    assert scanner.scan_opportunities() == 0
    assert captured == []


def test_muted_user_gets_no_alerts(plain_phone, captured, monkeypatch, uptrend):
    db.add_watch(plain_phone, "TEST", "اختبار")
    db.set_flag(plain_phone, "alerts_enabled", False)
    monkeypatch.setattr(scanner, "analyze", lambda s, **kw: analyze_frame(s, uptrend))
    monkeypatch.setattr(scanner, "run_task", lambda *a, **kw: "🔔 تنبيه")

    assert scanner.scan_opportunities() == 0


def test_data_failure_skips_symbol_quietly(plain_phone, captured, monkeypatch):
    db.add_watch(plain_phone, "BROKEN", "معطوب")

    def boom(*a, **kw):
        raise RuntimeError("انقطع الاتصال")

    monkeypatch.setattr(scanner, "analyze", boom)
    assert scanner.scan_opportunities() == 0          # لا يرمي استثناءً


# ------------------------------------------------------------ التنبيهات السعرية


def test_price_alert_fires_above(clean_db, phone, captured, monkeypatch):
    db.add_price_alert(phone, "GC=F", "above", 4000.0, "اختراق")
    monkeypatch.setattr(scanner, "get_quote", lambda s: type("Q", (), {"price": 4050.0})())

    assert scanner.check_price_alerts() == 1
    assert "تنبيه سعري" in captured[0][1]
    assert db.active_price_alerts(phone) == []        # لا يتكرر


def test_price_alert_does_not_fire_early(clean_db, phone, captured, monkeypatch):
    db.add_price_alert(phone, "GC=F", "above", 4000.0, None)
    monkeypatch.setattr(scanner, "get_quote", lambda s: type("Q", (), {"price": 3900.0})())

    assert scanner.check_price_alerts() == 0
    assert len(db.active_price_alerts(phone)) == 1


def test_price_alert_fires_below(clean_db, phone, captured, monkeypatch):
    db.add_price_alert(phone, "GC=F", "below", 3800.0, None)
    monkeypatch.setattr(scanner, "get_quote", lambda s: type("Q", (), {"price": 3750.0})())
    assert scanner.check_price_alerts() == 1


# ------------------------------------------------------------------ التذكيرات


def test_one_shot_reminder_fires_once(clean_db, phone, captured):
    from datetime import timedelta

    db.add_reminder(phone, "راجع محفظتك", due_at=db.now_utc() - timedelta(minutes=1))
    assert scanner.fire_reminders() == 1
    assert "راجع محفظتك" in captured[0][1]
    assert scanner.fire_reminders() == 0              # لا يتكرر


def test_future_reminder_does_not_fire(clean_db, phone, captured):
    from datetime import timedelta

    db.add_reminder(phone, "لاحقاً", due_at=db.now_utc() + timedelta(hours=2))
    assert scanner.fire_reminders() == 0


def test_daily_reminder_fires_once_per_day(clean_db, phone, captured):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo(settings.timezone)).strftime("%H:%M")
    db.add_reminder(phone, "تذكير يومي", repeat_daily=now)

    assert scanner.fire_reminders() == 1
    assert scanner.fire_reminders() == 0              # نفس اليوم
    assert len(db.list_reminders(phone)) == 1         # ويبقى نشطاً لبكرة


# -------------------------------------------------------------- صدمة إخبارية


def test_news_shock_deduplicates(clean_db, phone, captured, monkeypatch):
    from app.market import news as news_mod

    items = [{"العنوان": "الفيدرالي يخفض الفائدة", "الأهمية": "عالي"}]
    monkeypatch.setattr(news_mod, "breaking_risk_scan", lambda limit=6: items)
    monkeypatch.setattr(scanner, "run_task", lambda *a, **kw: "⚠️ خبر مهم")

    assert scanner.scan_news_shocks() == 1
    assert scanner.scan_news_shocks() == 0            # نفس الأخبار


def test_news_shock_respects_veto(clean_db, phone, captured, monkeypatch):
    from app.market import news as news_mod

    monkeypatch.setattr(news_mod, "breaking_risk_scan",
                        lambda limit=6: [{"العنوان": "خبر عادي", "الأهمية": "عالي"}])
    monkeypatch.setattr(scanner, "run_task", lambda *a, **kw: "تجاهل")

    assert scanner.scan_news_shocks() == 0
    assert captured == []


def test_owner_also_scans_core_symbols(clean_db, phone, captured, monkeypatch, uptrend):
    """صاحب الحساب يُراقَب معه المؤشرات والذهب والنفط حتى لو قائمته فارغة."""
    monkeypatch.setattr(scanner, "analyze", lambda s, **kw: analyze_frame(s, uptrend))
    monkeypatch.setattr(scanner, "run_task", lambda *a, **kw: "🔔 تنبيه")
    monkeypatch.setattr(scanner, "settings",
                        __import__("dataclasses").replace(settings, max_alerts_per_day=99))

    sent = scanner.scan_opportunities()
    assert sent == len(scanner.CORE_SYMBOLS)
