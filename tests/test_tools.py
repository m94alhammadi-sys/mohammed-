"""اختبارات أدوات الوكيل — كلها بدون إنترنت."""

import json

from app.tools.registry import TOOL_SCHEMAS, dispatch, server_tools


def run(name, args, phone):
    return json.loads(dispatch(name, args, phone))


# ------------------------------------------------------------ صحة التعريفات


def test_all_tools_have_valid_schema():
    for tool in TOOL_SCHEMAS:
        assert tool["name"] and tool["description"]
        schema = tool["input_schema"]
        assert schema["type"] == "object"
        for field in schema.get("required", []):
            assert field in schema["properties"], f"{tool['name']}: {field} غير معرّف"


def test_every_schema_has_a_handler():
    from app.tools.registry import _HANDLERS

    assert {t["name"] for t in TOOL_SCHEMAS} == set(_HANDLERS)


def test_server_tools_use_current_versions():
    types = {t["type"] for t in server_tools()}
    assert types == {"web_search_20260209", "web_fetch_20260209"}


def test_unknown_tool_returns_error(phone):
    assert "خطأ" in run("لا_توجد", {}, phone)


# -------------------------------------------------------- حاسبة إدارة المخاطر


def test_position_size_basic_math(clean_db, phone):
    out = run("position_size", {"capital": 100_000, "risk_percent": 1,
                                "entry": 8.50, "stop_loss": 8.10}, phone)
    assert out["المبلغ_المخاطر_به"] == 1000.0
    assert out["عدد_الوحدات"] == 2500.0            # 1000 / 0.40
    assert out["قيمة_المركز"] == 21250.0


def test_position_size_computes_reward_ratio(clean_db, phone):
    out = run("position_size", {"capital": 50_000, "risk_percent": 2, "entry": 100,
                                "stop_loss": 95, "target": 115}, phone)
    assert out["المخاطرة_للعائد"] == 3.0


def test_position_size_flags_poor_ratio(clean_db, phone):
    out = run("position_size", {"capital": 50_000, "risk_percent": 1, "entry": 100,
                                "stop_loss": 95, "target": 101}, phone)
    assert "ملاحظة" in out


def test_position_size_warns_on_oversized_position(clean_db, phone):
    out = run("position_size", {"capital": 10_000, "risk_percent": 5, "entry": 100,
                                "stop_loss": 99.9}, phone)
    assert "تحذير" in out


def test_position_size_rejects_zero_risk(clean_db, phone):
    assert "خطأ" in run("position_size", {"capital": 1000, "risk_percent": 1,
                                          "entry": 50, "stop_loss": 50}, phone)


def test_position_size_rejects_missing_fields(clean_db, phone):
    assert "خطأ" in run("position_size", {"capital": 1000}, phone)


# ------------------------------------------------------------ قائمة المتابعة


def test_watchlist_add_show_remove(clean_db, phone):
    added = run("manage_watchlist", {"action": "add", "symbols": ["إعمار", "الذهب"]}, phone)
    assert len(added["تمت_الإضافة"]) == 2

    shown = run("manage_watchlist", {"action": "show"}, phone)
    assert {row["الرمز"] for row in shown["القائمة"]} == {"EMAAR.DU", "GC=F"}

    run("manage_watchlist", {"action": "remove", "symbols": ["إعمار"]}, phone)
    shown = run("manage_watchlist", {"action": "show"}, phone)
    assert [row["الرمز"] for row in shown["القائمة"]] == ["GC=F"]


def test_watchlist_add_is_idempotent(clean_db, phone):
    run("manage_watchlist", {"action": "add", "symbols": ["إعمار"]}, phone)
    run("manage_watchlist", {"action": "add", "symbols": ["إعمار"]}, phone)
    shown = run("manage_watchlist", {"action": "show"}, phone)
    assert len(shown["القائمة"]) == 1


def test_empty_watchlist_reports_empty(clean_db, phone):
    assert run("manage_watchlist", {"action": "show"}, phone)["القائمة"] == "فارغة"


# ------------------------------------------------------------ التنبيهات السعرية


def test_price_alert_lifecycle(clean_db, phone):
    created = run("manage_price_alert", {"action": "set", "symbol": "إعمار",
                                         "direction": "above", "price": 9.0}, phone)
    alert_id = created["رقم_التنبيه"]

    listed = run("manage_price_alert", {"action": "list"}, phone)
    assert listed["التنبيهات_النشطة"][0]["رقم"] == alert_id

    run("manage_price_alert", {"action": "cancel", "alert_id": alert_id}, phone)
    assert run("manage_price_alert", {"action": "list"}, phone)["التنبيهات_النشطة"] == "لا توجد تنبيهات نشطة"


def test_price_alert_requires_fields(clean_db, phone):
    assert "خطأ" in run("manage_price_alert", {"action": "set", "symbol": "إعمار"}, phone)


def test_price_alert_rejects_bad_direction(clean_db, phone):
    out = run("manage_price_alert", {"action": "set", "symbol": "إعمار",
                                     "direction": "sideways", "price": 9}, phone)
    assert "خطأ" in out


# ------------------------------------------------------------------ التذكيرات


def test_reminder_relative_time(clean_db, phone):
    out = run("manage_reminder", {"action": "create", "text": "راجع المحفظة", "in_minutes": 60}, phone)
    assert "رقم_التذكير" in out


def test_reminder_daily_normalizes_time(clean_db, phone):
    out = run("manage_reminder", {"action": "create", "text": "الموجز", "daily_time": "8:5"}, phone)
    assert "08:05" in out["تم"]


def test_reminder_rejects_past_time(clean_db, phone):
    out = run("manage_reminder", {"action": "create", "text": "متأخر", "at": "2020-01-01 10:00"}, phone)
    assert "الماضي" in out["خطأ"]


def test_reminder_rejects_bad_format(clean_db, phone):
    out = run("manage_reminder", {"action": "create", "text": "خطأ", "at": "بكرة الصبح"}, phone)
    assert "خطأ" in out


def test_reminder_requires_a_time(clean_db, phone):
    assert "خطأ" in run("manage_reminder", {"action": "create", "text": "بدون وقت"}, phone)


def test_reminder_cancel(clean_db, phone):
    created = run("manage_reminder", {"action": "create", "text": "احذفني", "in_minutes": 30}, phone)
    run("manage_reminder", {"action": "cancel", "reminder_id": created["رقم_التذكير"]}, phone)
    assert run("manage_reminder", {"action": "list"}, phone)["التذكيرات"] == "لا توجد تذكيرات"


# -------------------------------------------------------------------- الذاكرة


def test_remember_and_recall(clean_db, phone):
    run("remember_fact", {"key": "أسلوب التداول", "value": "متوسط المدى"}, phone)
    assert clean_db.recall(phone)["أسلوب التداول"] == "متوسط المدى"


def test_remember_overwrites_same_key(clean_db, phone):
    run("remember_fact", {"key": "المحفظة", "value": "100 ألف"}, phone)
    run("remember_fact", {"key": "المحفظة", "value": "150 ألف"}, phone)
    assert clean_db.recall(phone)["المحفظة"] == "150 ألف"


def test_remember_requires_both_fields(clean_db, phone):
    assert "خطأ" in run("remember_fact", {"key": "ناقص"}, phone)


# --------------------------------------------------------------- بحث الرموز


def test_search_symbols_finds_group(clean_db, phone):
    results = run("search_symbols", {"query": "ادنوك"}, phone)["النتائج"]
    assert len(results) >= 3
    assert all("أدنوك" in r["الاسم_العربي"] for r in results)
