"""خادم الويب — يستقبل رسائل واتساب ويشغّل الجدولة."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, Request, Response

from . import db
from .brain import respond
from .config import normalize_phone, settings
from .scanner import scan_opportunities, send_brief
from .scheduler import job_status, start_scheduler, stop_scheduler
from .whatsapp import InboundMessage, get_provider
from .whatsapp.meta import MetaProvider

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("advisor")

WELCOME = (
    "أهلاً وسهلاً 👋\n\n"
    "أنا *المستشار* — خبيرك الاقتصادي على واتساب.\n\n"
    "أقدر أساعدك في:\n"
    "• تحليل الأسهم العالمية وأسهم الإمارات (أبوظبي ودبي)\n"
    "• الفوركس والذهب والنفط والعملات الرقمية\n"
    "• التحليل الفني والأساسي وقراءة الأخبار والسياسة\n"
    "• أنبهك تلقائياً لما تصير فرصة في السوق\n\n"
    "جرّب تسألني:\n"
    "_«وش رايك في سهم إعمار؟»_\n"
    "_«تابع لي الذهب ونبهني إذا نزل تحت 3900»_\n"
    "_«ذكرني الساعة 4 أراجع محفظتي»_\n"
    "_«شنو أهم شي بيأثر على السوق هالأسبوع؟»_"
)

UNSUPPORTED = (
    "أقدر أقرأ الرسائل النصية فقط حالياً. "
    "اكتب لي سؤالك نصاً وأخدمك 🙏"
)

DENIED = "عذراً، هذا الرقم غير مصرّح له باستخدام هذه الخدمة."


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    start_scheduler()
    log.info("المستشار الاقتصادي جاهز على المنفذ %s", settings.port)
    yield
    stop_scheduler()


app = FastAPI(title="المستشار الاقتصادي", version="1.0.0", lifespan=lifespan)


# ------------------------------------------------------------------ المعالجة


def _handle(message: InboundMessage) -> None:
    """يعالج رسالة واردة في الخلفية — واتساب يتوقع رد 200 خلال ثوانٍ."""
    provider = get_provider()
    phone = message.phone

    if not settings.is_allowed(phone):
        log.warning("رفض رسالة من رقم غير مصرّح: %s", phone)
        provider.send_text(phone, DENIED)
        return

    db.ensure_user(phone, message.name)
    db.touch_inbound(phone)                    # يفتح نافذة الـ 24 ساعة

    if message.kind != "text" or not message.text.strip():
        provider.send_text(phone, UNSUPPORTED)
        return

    text = message.text.strip()
    lowered = text.lower()

    # أوامر سريعة لا تحتاج النموذج
    if lowered in ("بدء", "ابدأ", "start", "مرحبا", "السلام عليكم", "هلا", "/start"):
        provider.send_text(phone, WELCOME)
        return
    if lowered in ("مسح", "امسح المحادثة", "/reset", "reset"):
        deleted = db.clear_history(phone)
        provider.send_text(phone, f"مسحت سجل المحادثة ({deleted} رسالة). نبدأ من جديد 🔄")
        return
    if lowered in ("إيقاف التنبيهات", "ايقاف التنبيهات", "/mute", "mute"):
        db.set_flag(phone, "alerts_enabled", False)
        provider.send_text(phone, "أوقفت التنبيهات التلقائية 🔕 — اكتب «تشغيل التنبيهات» لإرجاعها.")
        return
    if lowered in ("تشغيل التنبيهات", "/unmute", "unmute"):
        db.set_flag(phone, "alerts_enabled", True)
        provider.send_text(phone, "رجّعت التنبيهات التلقائية 🔔")
        return

    try:
        reply = respond(phone, text, message.name)
    except Exception as exc:
        log.exception("فشل توليد الرد لـ %s", phone)
        reply = f"صار خلل تقني عندي: {exc}\nجرّب مرة ثانية بعد شوي."

    provider.send_text(phone, reply)


# ------------------------------------------------------------------- المسارات


@app.get("/")
def root() -> dict:
    return {"الخدمة": "المستشار الاقتصادي", "الحالة": "يعمل", "المزوّد": settings.provider}


@app.get("/health")
def health() -> dict:
    return {
        "الحالة": "سليم",
        "المزوّد": settings.provider,
        "النموذج": settings.model,
        "المنطقة_الزمنية": settings.timezone,
        "عدد_المستخدمين": len(db.all_users()),
        "المهام_المجدولة": job_status(),
    }


@app.get("/webhook/whatsapp")
def verify_webhook(request: Request) -> Response:
    """تحقق Meta عند ربط الـ webhook لأول مرة."""
    params = request.query_params
    provider = get_provider()
    if isinstance(provider, MetaProvider):
        challenge = provider.verify_webhook(
            params.get("hub.mode", ""),
            params.get("hub.verify_token", ""),
            params.get("hub.challenge", ""),
        )
        if challenge:
            return Response(content=challenge, media_type="text/plain")
        log.warning("فشل التحقق من الـ webhook — رمز التحقق غير مطابق")
        return Response(content="رمز تحقق غير صحيح", status_code=403)
    return Response(content="ok", media_type="text/plain")


@app.post("/webhook/whatsapp")
async def receive_webhook(request: Request, background: BackgroundTasks) -> dict:
    """يستقبل الرسائل. نرد 200 فوراً ونعالج في الخلفية."""
    provider = get_provider()

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = await request.json()
    else:
        payload = dict(await request.form())

    try:
        messages = provider.parse_webhook(payload)
    except Exception:
        log.exception("فشل تحليل حمولة الـ webhook")
        return {"status": "ignored"}

    for message in messages:
        if message.phone:
            background.add_task(_handle, message)

    return {"status": "received", "count": len(messages)}


# ------------------------------------------- مسارات إدارية للاختبار اليدوي


@app.post("/admin/test-message")
async def test_message(request: Request) -> dict:
    """محاكاة رسالة واردة بدون واتساب — للاختبار المحلي.

    مثال: curl -X POST localhost:8000/admin/test-message \\
              -H 'content-type: application/json' \\
              -d '{"phone":"971500000000","text":"وش رايك في الذهب؟"}'
    """
    body = await request.json()
    phone = normalize_phone(body.get("phone") or settings.owner_number)
    text = body.get("text", "")
    if not (phone and text):
        return {"خطأ": "أحتاج phone و text"}

    db.ensure_user(phone)
    db.touch_inbound(phone)
    reply = respond(phone, text, body.get("name"))
    return {"الرد": reply}


@app.post("/admin/run/{job}")
def run_job(job: str) -> dict:
    """تشغيل مهمة مجدولة يدوياً: scan | morning | evening."""
    jobs = {
        "scan": scan_opportunities,
        "morning": lambda: send_brief("morning"),
        "evening": lambda: send_brief("evening"),
    }
    handler = jobs.get(job)
    if not handler:
        return {"خطأ": f"مهمة غير معروفة: {job}", "المتاح": list(jobs)}
    return {"المهمة": job, "النتيجة": handler()}
