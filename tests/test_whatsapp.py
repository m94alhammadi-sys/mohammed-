"""اختبارات طبقة واتساب: التقسيم، التنسيق، تحليل الـ webhook، ونافذة الـ 24 ساعة."""

from datetime import timedelta

from app import db
from app.whatsapp.base import MAX_LEN, split_message, to_whatsapp_markdown
from app.whatsapp.meta import MetaProvider
from app.whatsapp.twilio_provider import TwilioProvider


# ------------------------------------------------------------------ التقسيم


def test_short_message_not_split():
    assert split_message("رسالة قصيرة") == ["رسالة قصيرة"]


def test_empty_message_returns_empty_list():
    assert split_message("   ") == []


def test_long_message_respects_limit():
    text = "جملة اختبار طويلة. " * 500
    chunks = split_message(text, limit=1000)
    assert len(chunks) > 1
    assert all(len(c) <= 1000 for c in chunks)


def test_split_prefers_paragraph_boundaries():
    text = "الفقرة الأولى.\n\n" + "حشو. " * 200 + "\n\nالفقرة الأخيرة."
    chunks = split_message(text, limit=400)
    assert chunks[0].startswith("الفقرة الأولى")
    assert all(len(c) <= 400 for c in chunks)


def test_split_preserves_all_words():
    text = " ".join(f"كلمة{i}" for i in range(500))
    rejoined = " ".join(split_message(text, limit=300))
    assert rejoined.split() == text.split()


def test_default_limit_under_whatsapp_cap():
    assert MAX_LEN <= 4096


# ------------------------------------------------------------------ التنسيق


def test_markdown_bold_converted_to_whatsapp():
    assert to_whatsapp_markdown("**مهم**") == "*مهم*"


def test_headings_become_bold():
    assert to_whatsapp_markdown("## التحليل الفني") == "*التحليل الفني*"


def test_bullets_converted():
    assert "• دعم" in to_whatsapp_markdown("- دعم عند 8.10")


def test_existing_single_asterisk_preserved():
    assert to_whatsapp_markdown("*جاهز*") == "*جاهز*"


# ------------------------------------------------------- تحليل حمولة Meta


def meta_payload(body="مرحبا", kind="text", extra=None):
    message = {"from": "971500000000", "id": "wamid.TEST", "type": kind}
    message.update(extra or {"text": {"body": body}})
    return {"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": "971500000000", "profile": {"name": "محمد"}}],
        "messages": [message],
    }}]}]}


def test_meta_parses_text_message():
    parsed = MetaProvider("t", "1").parse_webhook(meta_payload("شحال سعر إعمار؟"))
    assert len(parsed) == 1
    assert parsed[0].phone == "971500000000"
    assert parsed[0].name == "محمد"
    assert parsed[0].text == "شحال سعر إعمار؟"
    assert parsed[0].kind == "text"


def test_meta_parses_interactive_reply():
    payload = meta_payload(kind="interactive", extra={
        "interactive": {"button_reply": {"id": "b1", "title": "التحليل الفني"}}})
    parsed = MetaProvider("t", "1").parse_webhook(payload)
    assert parsed[0].text == "التحليل الفني"


def test_meta_marks_audio_unsupported():
    payload = meta_payload(kind="audio", extra={"audio": {"id": "a1"}})
    parsed = MetaProvider("t", "1").parse_webhook(payload)
    assert parsed[0].kind == "audio"
    assert parsed[0].text == ""


def test_meta_ignores_status_only_payload():
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"status": "delivered"}]}}]}]}
    assert MetaProvider("t", "1").parse_webhook(payload) == []


def test_meta_handles_empty_payload():
    assert MetaProvider("t", "1").parse_webhook({}) == []


def test_meta_verify_webhook():
    from app.config import settings

    provider = MetaProvider("t", "1")
    assert provider.verify_webhook("subscribe", settings.meta_verify_token, "CH") == "CH"
    assert provider.verify_webhook("subscribe", "wrong", "CH") is None
    assert provider.verify_webhook("unsubscribe", settings.meta_verify_token, "CH") is None


# ----------------------------------------------------- تحليل حمولة Twilio


def test_twilio_parses_form_payload():
    parsed = TwilioProvider("AC", "tok", "whatsapp:+1").parse_webhook({
        "From": "whatsapp:+971500000000", "Body": "وش أخبار الذهب",
        "ProfileName": "محمد", "MessageSid": "SM1",
    })
    assert parsed[0].phone == "971500000000"
    assert parsed[0].text == "وش أخبار الذهب"


def test_twilio_ignores_payload_without_sender():
    assert TwilioProvider("AC", "tok", "whatsapp:+1").parse_webhook({"Body": "يتيمة"}) == []


# ------------------------------------------------------ نافذة الـ 24 ساعة


def test_service_window_open_after_inbound(clean_db, phone):
    db.touch_inbound(phone)
    assert db.within_service_window(phone) is True


def test_service_window_closed_after_24h(clean_db, phone):
    stale = db.iso(db.now_utc() - timedelta(hours=25))
    with db.tx() as conn:
        conn.execute("UPDATE users SET last_inbound_at = ? WHERE phone = ?", (stale, phone))
    assert db.within_service_window(phone) is False


def test_service_window_closed_for_new_user(clean_db):
    db.ensure_user("971509999999")
    assert db.within_service_window("971509999999") is False
