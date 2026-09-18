"""اختبارات التخزين — خاصة سلامة سجل المحادثة عند القص."""

from app import db


def test_history_starts_at_a_user_anchor(clean_db, phone):
    """القص يجب ألا يفصل tool_result عن tool_use — نرجع لأقرب رسالة مستخدم."""
    db.save_message(phone, "user", [{"type": "text", "text": "حلل إعمار"}], is_anchor=True)
    db.save_message(phone, "assistant", [{"type": "tool_use", "id": "t1", "name": "get_price", "input": {}}])
    db.save_message(phone, "user", [{"type": "tool_result", "tool_use_id": "t1", "content": "{}"}])
    db.save_message(phone, "assistant", [{"type": "text", "text": "السعر كذا"}])

    history = db.load_history(phone, max_messages=3)      # قص يقطع وسط الدورة
    assert history[0]["role"] == "user"
    assert history[0]["content"][0]["type"] == "text"


def test_history_returns_empty_when_no_anchor_in_window(clean_db, phone):
    db.save_message(phone, "assistant", [{"type": "text", "text": "بدون مرساة"}])
    assert db.load_history(phone) == []


def test_history_roundtrips_content(clean_db, phone):
    blocks = [{"type": "text", "text": "نص عربي مع رموز: 📈"}]
    db.save_message(phone, "user", blocks, is_anchor=True)
    assert db.load_history(phone)[0]["content"] == blocks


def test_clear_history(clean_db, phone):
    db.save_message(phone, "user", [{"type": "text", "text": "أ"}], is_anchor=True)
    assert db.clear_history(phone) == 1
    assert db.load_history(phone) == []


def test_alert_cooldown(clean_db, phone):
    db.record_alert(phone, "EMAAR.DU", "اختراق", 80.0, {})
    assert db.alert_on_cooldown(phone, "EMAAR.DU", "اختراق", hours=6) is True
    assert db.alert_on_cooldown(phone, "EMAAR.DU", "انعكاس", hours=6) is False
    assert db.alert_on_cooldown(phone, "FAB.AD", "اختراق", hours=6) is False


def test_daily_alert_counter(clean_db, phone):
    for _ in range(3):
        db.record_alert(phone, "GC=F", "زخم", 75.0, {})
    assert db.alerts_sent_today(phone) == 3


def test_alerts_flag_filters_users(clean_db, phone):
    db.ensure_user("971501111111")
    db.set_flag("971501111111", "alerts_enabled", False)
    phones = {u["phone"] for u in db.all_users(only_alerts=True)}
    assert phone in phones and "971501111111" not in phones


def test_phone_normalization(clean_db):
    db.ensure_user("+971 50 123 4567", "تجربة")
    assert db.get_user("971501234567") is not None


def test_price_alert_fire_deactivates(clean_db, phone):
    alert_id = db.add_price_alert(phone, "GC=F", "above", 4000.0, None)
    db.fire_price_alert(alert_id)
    assert db.active_price_alerts(phone) == []


def test_history_reaches_back_past_window_for_anchor(clean_db, phone):
    """لو وقعت نافذة القص كلها داخل دورة أدوات، نوسّعها للخلف بدل إسقاط السجل."""
    db.save_message(phone, "user", [{"type": "text", "text": "حلل إعمار"}], is_anchor=True)
    for i in range(6):
        db.save_message(phone, "assistant", [{"type": "tool_use", "id": f"t{i}", "name": "x", "input": {}}])
        db.save_message(phone, "user", [{"type": "tool_result", "tool_use_id": f"t{i}", "content": "{}"}])

    history = db.load_history(phone, max_messages=4)
    assert history[0]["content"][0]["type"] == "text"
    assert len(history) == 13                       # المرساة + 12 رسالة أدوات


def test_history_falls_forward_when_backward_window_too_large(clean_db, phone):
    """لا نعيد سجلاً ضخماً: إن بعُدت المرساة السابقة نبدأ من المرساة التالية."""
    db.save_message(phone, "user", [{"type": "text", "text": "سؤال قديم"}], is_anchor=True)
    for i in range(30):
        db.save_message(phone, "assistant", [{"type": "text", "text": f"رد {i}"}])
    db.save_message(phone, "user", [{"type": "text", "text": "سؤال جديد"}], is_anchor=True)
    db.save_message(phone, "assistant", [{"type": "text", "text": "رد جديد"}])

    history = db.load_history(phone, max_messages=5)
    assert history[0]["content"][0]["text"] == "سؤال جديد"
    assert len(history) == 2
