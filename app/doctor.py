"""أداة فحص الإعدادات — تقول لك بالضبط وش ناقص قبل ما تربط واتساب.

الاستخدام:  python -m app.doctor
"""

from __future__ import annotations

import sys

from .config import settings

OK, FAIL, WARN, INFO = "✅", "❌", "⚠️ ", "ℹ️ "

_problems: list[str] = []
_warnings: list[str] = []


def _line(icon: str, title: str, detail: str = "") -> None:
    print(f"{icon} {title}")
    if detail:
        for row in detail.strip().split("\n"):
            print(f"      {row}")


def _fail(title: str, fix: str) -> None:
    _line(FAIL, title, fix)
    _problems.append(title)


def _warn(title: str, fix: str) -> None:
    _line(WARN, title, fix)
    _warnings.append(title)


# ---------------------------------------------------------------- الفحوصات


def check_env_file() -> None:
    from .config import BASE_DIR

    if (BASE_DIR / ".env").exists():
        _line(OK, "ملف .env موجود")
    else:
        _fail("ملف .env غير موجود", "شغّل:  cp .env.example .env  ثم عبّي المفاتيح")


def check_anthropic() -> None:
    key = settings.anthropic_api_key
    if not key:
        _fail("مفتاح Anthropic غير مضبوط",
              "احصل عليه من console.anthropic.com وضعه في .env:\nANTHROPIC_API_KEY=sk-ant-...")
        return
    if not key.startswith("sk-ant-"):
        _warn("شكل مفتاح Anthropic غير معتاد", "المفتاح الصحيح يبدأ بـ sk-ant-")

    print(f"{INFO}أجرّب الاتصال بـ Claude ({settings.model})…")
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=key)
        client.messages.create(
            model=settings.model,
            max_tokens=16,
            messages=[{"role": "user", "content": "قل: جاهز"}],
        )
        _line(OK, f"مفتاح Anthropic يعمل — النموذج {settings.model}")
    except Exception as exc:
        _fail(f"فشل الاتصال بـ Claude: {type(exc).__name__}",
              f"{str(exc)[:200]}\nتأكد من صحة المفتاح ومن وجود رصيد في حسابك.")


def check_meta() -> None:
    missing = [
        name for name, value in (
            ("META_ACCESS_TOKEN", settings.meta_access_token),
            ("META_PHONE_NUMBER_ID", settings.meta_phone_number_id),
            ("META_VERIFY_TOKEN", settings.meta_verify_token),
        ) if not value
    ]
    if missing:
        _fail(f"إعدادات Meta ناقصة: {'، '.join(missing)}",
              "من developers.facebook.com ← تطبيقك ← WhatsApp ← API Setup")
        return

    print(f"{INFO}أجرّب الاتصال بواتساب…")
    try:
        import httpx

        response = httpx.get(
            f"https://graph.facebook.com/v21.0/{settings.meta_phone_number_id}",
            params={"fields": "display_phone_number,verified_name,quality_rating"},
            headers={"Authorization": f"Bearer {settings.meta_access_token}"},
            timeout=20.0,
        )
        if response.status_code == 200:
            data = response.json()
            _line(OK, "الاتصال بواتساب يعمل",
                  f"الرقم: {data.get('display_phone_number', '—')}\n"
                  f"الاسم: {data.get('verified_name', '—')}\n"
                  f"الجودة: {data.get('quality_rating', '—')}")
        elif response.status_code in (400, 401):
            _fail("توكن Meta غير صالح أو منتهي",
                  "توكن التجربة يعيش 24 ساعة فقط.\n"
                  "للإنتاج أنشئ توكناً دائماً من:\n"
                  "business.facebook.com ← Business Settings ← System Users")
        else:
            _fail(f"واتساب رفض الطلب ({response.status_code})", response.text[:250])
    except Exception as exc:
        _fail(f"تعذّر الوصول لواتساب: {type(exc).__name__}", str(exc)[:200])


def check_twilio() -> None:
    missing = [
        name for name, value in (
            ("TWILIO_ACCOUNT_SID", settings.twilio_account_sid),
            ("TWILIO_AUTH_TOKEN", settings.twilio_auth_token),
            ("TWILIO_WHATSAPP_FROM", settings.twilio_whatsapp_from),
        ) if not value
    ]
    if missing:
        _fail(f"إعدادات Twilio ناقصة: {'، '.join(missing)}", "من console.twilio.com")
        return

    if not settings.twilio_whatsapp_from.startswith("whatsapp:"):
        _fail("صيغة TWILIO_WHATSAPP_FROM خاطئة",
              "لازم تبدأ بـ whatsapp: — مثال:\nTWILIO_WHATSAPP_FROM=whatsapp:+14155238886")
        return

    print(f"{INFO}أجرّب الاتصال بـ Twilio…")
    try:
        import httpx

        response = httpx.get(
            f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}.json",
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            timeout=20.0,
        )
        if response.status_code == 200:
            _line(OK, f"الاتصال بـ Twilio يعمل — الحساب {response.json().get('friendly_name', '—')}")
        else:
            _fail(f"Twilio رفض الطلب ({response.status_code})",
                  "تأكد من SID والتوكن في console.twilio.com")
    except Exception as exc:
        _fail(f"تعذّر الوصول لـ Twilio: {type(exc).__name__}", str(exc)[:200])


def check_security() -> None:
    if settings.allowed_numbers:
        _line(OK, f"الأرقام المصرّح لها: {len(settings.allowed_numbers)} رقم",
              "، ".join(settings.allowed_numbers))
    else:
        _warn("ALLOWED_NUMBERS فارغ — أي رقم يقدر يستخدم الوكيل على حسابك",
              "ضع رقمك في .env:\nALLOWED_NUMBERS=971500000000")

    if settings.owner_number:
        _line(OK, f"رقم صاحب الحساب: {settings.owner_number}")
    else:
        _warn("OWNER_NUMBER فارغ — لن تصلك الموجزات اليومية",
              "ضع رقمك في .env:\nOWNER_NUMBER=971500000000")

    if settings.owner_number and settings.allowed_numbers:
        if settings.owner_number not in settings.allowed_numbers:
            _warn("رقمك غير موجود في ALLOWED_NUMBERS",
                  "أضفه وإلا لن تقدر تكلم الوكيل")


def check_storage() -> None:
    try:
        from . import db

        db.init_db()
        _line(OK, f"قاعدة البيانات جاهزة: {settings.db_file}")
    except Exception as exc:
        _fail(f"تعذّر إنشاء قاعدة البيانات: {exc}",
              f"تأكد من صلاحيات الكتابة في {settings.db_file.parent}")


def check_market_data() -> None:
    print(f"{INFO}أجرّب جلب سعر من السوق…")
    try:
        from .market.data import get_quote

        quote = get_quote("AAPL")
        _line(OK, f"بيانات السوق تعمل — آبل عند {quote.price:.2f} ({quote.as_of})")
    except Exception as exc:
        _warn(f"تعذّر جلب بيانات السوق: {type(exc).__name__}",
              f"{str(exc)[:180]}\n"
              "قد يكون الاتصال محجوباً على شبكتك. الوكيل سيرد لكن بدون أسعار.")


def print_webhook_help() -> None:
    print()
    print("─" * 62)
    print("🔗 رابط الـ webhook الذي تحتاجه")
    print("─" * 62)
    print(f"""
الخادم يستمع محلياً على:  http://localhost:{settings.port}

واتساب لازم يوصل لك من الإنترنت، فتحتاج رابطاً عاماً:

  الطريقة السريعة (للتجربة):
      ngrok http {settings.port}
      ← ستحصل على رابط مثل  https://ab12cd.ngrok-free.app

  ضع في إعدادات واتساب:
      Callback URL:   https://<رابطك>/webhook/whatsapp
      Verify Token:   {settings.meta_verify_token or '(اضبط META_VERIFY_TOKEN أولاً)'}
""".rstrip())


def main() -> int:
    # نكتم سجلات المكتبات الخارجية حتى تبقى نتيجة الفحص واضحة
    import logging

    logging.disable(logging.ERROR)   # yfinance يسجّل أخطاء الشبكة على مستوى ERROR

    print()
    print("═" * 62)
    print("   🩺  فحص إعدادات المستشار الاقتصادي")
    print("═" * 62)
    print()

    print("【 1 】 الإعدادات الأساسية")
    check_env_file()
    check_storage()
    print()

    print("【 2 】 عقل الوكيل (Claude)")
    check_anthropic()
    print()

    print(f"【 3 】 واتساب — المزوّد المختار: {settings.provider}")
    if settings.provider == "twilio":
        check_twilio()
    else:
        check_meta()
    print()

    print("【 4 】 الأمان")
    check_security()
    print()

    print("【 5 】 بيانات السوق")
    check_market_data()

    print_webhook_help()

    print()
    print("═" * 62)
    if _problems:
        print(f"   {FAIL} توقفنا عند {len(_problems)} مشكلة لازم تُحل:")
        for problem in _problems:
            print(f"      • {problem}")
        print()
        print("   صلّحها في ملف .env وأعد تشغيل:  python -m app.doctor")
        print("═" * 62)
        print()
        return 1

    if _warnings:
        print(f"   {OK} كل شي أساسي شغال، لكن عندك {len(_warnings)} ملاحظة:")
        for warning in _warnings:
            print(f"      • {warning}")
    else:
        print(f"   {OK} كل شي جاهز! شغّل الوكيل:  ./run.sh")
    print("═" * 62)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
