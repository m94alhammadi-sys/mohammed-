"""اختبارات أداة الفحص — تتأكد أنها تكشف النقص وتُرجع الرمز الصحيح."""

import pytest

from app import doctor


@pytest.fixture(autouse=True)
def reset_state():
    doctor._problems.clear()
    doctor._warnings.clear()
    yield
    doctor._problems.clear()
    doctor._warnings.clear()


def test_missing_anthropic_key_is_a_blocking_problem(monkeypatch):
    from dataclasses import replace

    monkeypatch.setattr(doctor, "settings", replace(doctor.settings, anthropic_api_key=""))
    doctor.check_anthropic()
    assert len(doctor._problems) == 1


def test_missing_meta_config_lists_every_missing_field(monkeypatch, capsys):
    from dataclasses import replace

    monkeypatch.setattr(doctor, "settings", replace(
        doctor.settings, meta_access_token="", meta_phone_number_id="", meta_verify_token=""))
    doctor.check_meta()

    output = capsys.readouterr().out
    for field in ("META_ACCESS_TOKEN", "META_PHONE_NUMBER_ID", "META_VERIFY_TOKEN"):
        assert field in output
    assert len(doctor._problems) == 1


def test_twilio_rejects_sender_without_prefix(monkeypatch, capsys):
    from dataclasses import replace

    monkeypatch.setattr(doctor, "settings", replace(
        doctor.settings, twilio_account_sid="AC1", twilio_auth_token="tok",
        twilio_whatsapp_from="+14155238886"))       # ناقص whatsapp:
    doctor.check_twilio()

    assert "whatsapp:" in capsys.readouterr().out
    assert len(doctor._problems) == 1


def test_empty_allowlist_is_a_warning_not_a_blocker(monkeypatch):
    from dataclasses import replace

    monkeypatch.setattr(doctor, "settings", replace(
        doctor.settings, allowed_numbers=[], owner_number="971500000000"))
    doctor.check_security()

    assert doctor._problems == []
    assert len(doctor._warnings) == 1


def test_owner_missing_from_allowlist_is_flagged(monkeypatch, capsys):
    from dataclasses import replace

    monkeypatch.setattr(doctor, "settings", replace(
        doctor.settings, allowed_numbers=["971501111111"], owner_number="971502222222"))
    doctor.check_security()

    assert "غير موجود في ALLOWED_NUMBERS" in capsys.readouterr().out


def test_consistent_security_config_passes(monkeypatch):
    from dataclasses import replace

    monkeypatch.setattr(doctor, "settings", replace(
        doctor.settings, allowed_numbers=["971500000000"], owner_number="971500000000"))
    doctor.check_security()

    assert doctor._problems == [] and doctor._warnings == []


def test_market_data_failure_is_a_warning_only(monkeypatch):
    """انقطاع مصدر الأسعار لا يمنع تشغيل الوكيل — تحذير لا خطأ."""
    import app.market.data as data

    def boom(symbol):
        raise RuntimeError("الشبكة محجوبة")

    monkeypatch.setattr(data, "get_quote", boom)
    doctor.check_market_data()

    assert doctor._problems == []
    assert len(doctor._warnings) == 1


def test_storage_check_passes(clean_db):
    doctor.check_storage()
    assert doctor._problems == []


def test_webhook_help_prints_the_full_path(capsys):
    doctor.print_webhook_help()
    assert "/webhook/whatsapp" in capsys.readouterr().out


def test_main_returns_error_code_when_blocked(monkeypatch):
    monkeypatch.setattr(doctor, "check_env_file", lambda: doctor._fail("عطل", "صلّحه"))
    monkeypatch.setattr(doctor, "check_storage", lambda: None)
    monkeypatch.setattr(doctor, "check_anthropic", lambda: None)
    monkeypatch.setattr(doctor, "check_meta", lambda: None)
    monkeypatch.setattr(doctor, "check_twilio", lambda: None)
    monkeypatch.setattr(doctor, "check_security", lambda: None)
    monkeypatch.setattr(doctor, "check_market_data", lambda: None)

    assert doctor.main() == 1


def test_main_returns_zero_when_healthy(monkeypatch):
    for check in ("check_env_file", "check_storage", "check_anthropic", "check_meta",
                  "check_twilio", "check_security", "check_market_data"):
        monkeypatch.setattr(doctor, check, lambda: None)

    assert doctor.main() == 0
