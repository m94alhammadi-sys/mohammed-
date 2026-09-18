"""اختبارات مسارات الخادم و webhook واتساب."""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import settings


@pytest.fixture
def client(clean_db, monkeypatch):
    """خادم اختبار: النموذج ومزوّد واتساب كلاهما مُحاكى."""
    import app.main as main

    sent = []

    class FakeProvider:
        name = "fake"

        def send_text(self, phone, text):
            sent.append((phone, text))
            return ["msg-1"]

        def send_template(self, phone, template, params):
            sent.append((phone, f"[قالب {template}] {params}"))
            return "msg-1"

        def send(self, phone, text, in_window=True, template=None):
            return self.send_text(phone, text)

        def parse_webhook(self, payload):
            from app.whatsapp.meta import MetaProvider

            return MetaProvider("t", "1").parse_webhook(payload)

        def verify_webhook(self, mode, token, challenge):
            from app.whatsapp.meta import MetaProvider

            return MetaProvider("t", "1").verify_webhook(mode, token, challenge)

    provider = FakeProvider()
    monkeypatch.setattr(main, "get_provider", lambda: provider)
    monkeypatch.setattr(main, "MetaProvider", FakeProvider)
    monkeypatch.setattr(main, "respond", lambda phone, text, name=None: f"رد على: {text}")

    with TestClient(main.app) as test_client:
        test_client.sent = sent
        yield test_client


def inbound(text, sender="971500000000"):
    return {"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": sender, "profile": {"name": "محمد"}}],
        "messages": [{"from": sender, "id": "wamid.1", "type": "text", "text": {"body": text}}],
    }}]}]}


# -------------------------------------------------------------------- الصحة


def test_root_endpoint(client):
    assert client.get("/").json()["الحالة"] == "يعمل"


def test_health_lists_scheduled_jobs(client):
    body = client.get("/health").json()
    ids = {job["المهمة"] for job in body["المهام_المجدولة"]}
    assert {"reminders", "price_alerts", "opportunities", "morning_brief"} <= ids


# ------------------------------------------------------------ تحقق الـ webhook


def test_webhook_verification_accepts_correct_token(client):
    response = client.get("/webhook/whatsapp", params={
        "hub.mode": "subscribe",
        "hub.verify_token": settings.meta_verify_token,
        "hub.challenge": "CHALLENGE-123",
    })
    assert response.status_code == 200
    assert response.text == "CHALLENGE-123"


def test_webhook_verification_rejects_wrong_token(client):
    response = client.get("/webhook/whatsapp", params={
        "hub.mode": "subscribe", "hub.verify_token": "خطأ", "hub.challenge": "X",
    })
    assert response.status_code == 403


# ---------------------------------------------------------- استقبال الرسائل


def test_message_reaches_the_brain(client, phone):
    client.post("/webhook/whatsapp", json=inbound("وش رايك في الذهب؟"))
    assert client.sent[-1] == (phone, "رد على: وش رايك في الذهب؟")


def test_inbound_opens_the_service_window(client, phone):
    client.post("/webhook/whatsapp", json=inbound("هلا"))
    assert db.within_service_window(phone) is True


def test_welcome_command_skips_the_model(client, phone):
    client.post("/webhook/whatsapp", json=inbound("بدء"))
    assert "المستشار" in client.sent[-1][1]
    assert "رد على" not in client.sent[-1][1]


def test_mute_and_unmute_commands(client, phone):
    client.post("/webhook/whatsapp", json=inbound("إيقاف التنبيهات"))
    assert db.get_user(phone)["alerts_enabled"] == 0

    client.post("/webhook/whatsapp", json=inbound("تشغيل التنبيهات"))
    assert db.get_user(phone)["alerts_enabled"] == 1


def test_reset_command_clears_history(client, phone):
    db.save_message(phone, "user", [{"type": "text", "text": "قديم"}], is_anchor=True)
    client.post("/webhook/whatsapp", json=inbound("مسح"))
    assert db.load_history(phone) == []


def test_unauthorized_number_is_rejected(client):
    client.post("/webhook/whatsapp", json=inbound("هلا", sender="19998887777"))
    assert "غير مصرّح" in client.sent[-1][1]


def test_non_text_message_gets_guidance(client, phone):
    payload = {"entry": [{"changes": [{"value": {
        "messages": [{"from": phone, "id": "w1", "type": "audio", "audio": {"id": "a1"}}],
    }}]}]}
    client.post("/webhook/whatsapp", json=payload)
    assert "النصية" in client.sent[-1][1]


def test_status_only_payload_is_ignored(client):
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"status": "read"}]}}]}]}
    assert client.post("/webhook/whatsapp", json=payload).json()["count"] == 0


def test_malformed_payload_does_not_crash(client):
    assert client.post("/webhook/whatsapp", json={"غريب": True}).status_code == 200


def test_brain_failure_is_reported_not_swallowed(client, phone, monkeypatch):
    import app.main as main

    def boom(*a, **kw):
        raise RuntimeError("انقطع الاتصال بالنموذج")

    monkeypatch.setattr(main, "respond", boom)
    client.post("/webhook/whatsapp", json=inbound("حلل لي"))
    assert "خلل تقني" in client.sent[-1][1]


# ---------------------------------------------------------- مسارات إدارية


def test_admin_test_message(client, phone):
    response = client.post("/admin/test-message", json={"phone": phone, "text": "تجربة"})
    assert response.json()["الرد"] == "رد على: تجربة"


def test_admin_test_message_requires_fields(client):
    assert "خطأ" in client.post("/admin/test-message", json={"phone": ""}).json()


def test_admin_unknown_job(client):
    assert "خطأ" in client.post("/admin/run/غير-موجود").json()
