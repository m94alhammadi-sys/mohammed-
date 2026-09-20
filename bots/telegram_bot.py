"""بوت تيليجرام للمستشار المالي.

يعمل بنظام long-polling: لا يحتاج سيرفر عام ولا دومين — يكفي تشغيله على أي
جهاز أو خادم صغير.
"""

from __future__ import annotations

import asyncio
import html
import logging
from datetime import time as dtime
from zoneinfo import ZoneInfo

from telegram import BotCommand, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from advisor.brain import AdvisorBrain
from advisor.config import settings
from advisor.service import AdvisorService
from advisor.storage import HORIZONS, RISK_PROFILES, Storage
from advisor.text import split_message

log = logging.getLogger(__name__)

TELEGRAM_LIMIT = 4000  # الحد الرسمي 4096، نترك هامشاً

WELCOME = """أهلاً بك 👋 أنا <b>راصد</b> — مستشارك المالي والاقتصادي.

أتابع لك: الأسواق العالمية 🇺🇸🇪🇺، السوق الإماراتي 🇦🇪، الذهب والسلع والعملات 🥇، والعملات الرقمية ₿
وأبحث في الإنترنت لحظياً قبل أي رقم أو توصية.

<b>ابدأ من هنا:</b>
/brief — إحاطة الأسواق الآن
/news — آخر الأخبار وأثرها
/market — لقطة أسعار سريعة
/analyze BTC — تحليل أصل معيّن
/risk — اضبط مستوى المخاطر والأفق الزمني
/daily on — إحاطة تصلك كل صباح

أو اكتب لي سؤالك مباشرة، مثل: «وش أثر قرار الفيدرالي على الذهب؟»

⚠️ تحليل تعليمي وليس استشارة مالية مرخّصة."""

HELP = """<b>الأوامر</b>

<b>التحليل والأخبار</b>
/brief — الإحاطة اليومية الكاملة
/news — أهم ٥ أخبار وأثرها
/market — أسعار مباشرة بدون تحليل
/analyze &lt;رمز&gt; — تحليل معمّق (مثال: /analyze XAUUSD)

<b>المحفظة والمتابعة</b>
/add &lt;رمز&gt; &lt;كمية&gt; [سعر الشراء] — إضافة مركز
/remove &lt;رمز&gt; — حذف مركز
/portfolio — مراجعة المحفظة بالكامل
/watch &lt;رمز&gt; — إضافة لقائمة المتابعة
/unwatch &lt;رمز&gt; — حذف من المتابعة
/list — عرض المتابعة والمحفظة

<b>الإعدادات</b>
/risk &lt;محافظ|متوازن|مخاطرة عالية&gt;
/horizon &lt;قصير المدى|متوسط المدى|طويل المدى&gt;
/capital &lt;ملاحظة&gt; — مثال: /capital رأس مال 50 ألف درهم، لا أستخدم رافعة
/daily on|off — الإحاطة الصباحية التلقائية
/reset — مسح ذاكرة المحادثة

أو اسألني أي سؤال مباشرة بالعربي."""


# ── أدوات مساعدة ─────────────────────────────────────────────
def _chunks(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """تقسيم الرد الطويل على رسائل ضمن حد تيليجرام."""
    return split_message(text, limit)


async def _send(update: Update, text: str, parse_mode: str | None = None) -> None:
    for chunk in _chunks(text):
        await update.effective_message.reply_text(chunk, parse_mode=parse_mode,
                                                  disable_web_page_preview=True)


def _service(context: ContextTypes.DEFAULT_TYPE) -> AdvisorService:
    return context.application.bot_data["service"]


async def _guard(update: Update) -> bool:
    """قائمة السماح: لو مفعّلة، يُرفض من ليس فيها."""
    user = update.effective_user
    if user and settings.is_allowed(user.id):
        return True
    if update.effective_message:
        await update.effective_message.reply_text(
            "هذا البوت خاص. لو تملكه، أضف رقم معرّفك في ADVISOR_ALLOWED_USER_IDS.\n"
            f"معرّفك: {user.id if user else 'غير معروف'}"
        )
    return False


async def _profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = (user.full_name if user else "") or ""
    return await _service(context).storage.ensure_user(user.id, name)


async def _thinking(update: Update, context: ContextTypes.DEFAULT_TYPE, note: str):
    """رسالة انتظار + مؤشر كتابة، لأن البحث والتحليل يستغرقان وقتاً."""
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    return await update.effective_message.reply_text(note)


async def _deliver(update: Update, placeholder, reply) -> None:
    try:
        await placeholder.delete()
    except TelegramError:
        pass
    await _send(update, reply.formatted())


# ── الأوامر ──────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    await _profile(update, context)
    await _send(update, WELCOME, ParseMode.HTML)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    await _send(update, HELP, ParseMode.HTML)


async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    profile = await _profile(update, context)
    placeholder = await _thinking(update, context, "📡 أجمع الأسعار وأبحث في أخبار آخر ٢٤ ساعة…")
    reply = await _service(context).daily_brief(profile)
    await _deliver(update, placeholder, reply)


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    profile = await _profile(update, context)
    placeholder = await _thinking(update, context, "📰 أبحث في آخر الأخبار…")
    reply = await _service(context).news_digest(profile)
    await _deliver(update, placeholder, reply)


async def cmd_market(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    text = await _service(context).market_snapshot_text()
    await _send(update, text, ParseMode.HTML)


async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    if not context.args:
        await _send(update, "اكتب الرمز بعد الأمر. مثال: /analyze BTC أو /analyze XAUUSD")
        return
    profile = await _profile(update, context)
    symbol = context.args[0].upper()
    placeholder = await _thinking(update, context, f"🔍 أحلّل {html.escape(symbol)} وأبحث عن آخر أخباره…")
    reply = await _service(context).analyze_symbol(profile, symbol)
    await _deliver(update, placeholder, reply)


async def cmd_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    profile = await _profile(update, context)
    placeholder = await _thinking(update, context, "🧮 أراجع مراكزك وأبحث عن مستجداتها…")
    reply = await _service(context).portfolio_review(profile)
    await _deliver(update, placeholder, reply)


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    if len(context.args) < 2:
        await _send(update, "الصيغة: /add <رمز> <كمية> [سعر الشراء]\nمثال: /add BTC 0.5 61000")
        return
    profile = await _profile(update, context)
    symbol = context.args[0].upper()
    try:
        quantity = float(context.args[1])
    except ValueError:
        await _send(update, "الكمية لازم تكون رقماً. مثال: /add BTC 0.5 61000")
        return
    avg_price = None
    if len(context.args) >= 3:
        try:
            avg_price = float(context.args[2])
        except ValueError:
            await _send(update, "سعر الشراء لازم يكون رقماً.")
            return
    note = " ".join(context.args[3:])
    await _service(context).storage.upsert_holding(profile.user_id, symbol, quantity, avg_price, note)
    await _send(update, f"✅ تم تسجيل {symbol}: كمية {quantity}"
                        + (f" بمتوسط سعر {avg_price}" if avg_price else "")
                        + "\nراجع محفظتك بالأمر /portfolio")


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    if not context.args:
        await _send(update, "الصيغة: /remove <رمز>")
        return
    profile = await _profile(update, context)
    symbol = context.args[0].upper()
    await _service(context).storage.remove_holding(profile.user_id, symbol)
    await _send(update, f"🗑️ تم حذف {symbol} من المحفظة.")


async def cmd_watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    if not context.args:
        await _send(update, "الصيغة: /watch <رمز>\nمثال: /watch EMAAR.AE")
        return
    profile = await _profile(update, context)
    for symbol in context.args:
        await _service(context).storage.add_watch(profile.user_id, symbol)
    await _send(update, "👁️ أضفت: " + "، ".join(s.upper() for s in context.args))


async def cmd_unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    if not context.args:
        await _send(update, "الصيغة: /unwatch <رمز>")
        return
    profile = await _profile(update, context)
    await _service(context).storage.remove_watch(profile.user_id, context.args[0])
    await _send(update, f"تم حذف {context.args[0].upper()} من قائمة المتابعة.")


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    profile = await _profile(update, context)
    storage = _service(context).storage
    watchlist = await storage.get_watchlist(profile.user_id)
    holdings = await storage.get_holdings(profile.user_id)

    lines = ["<b>ملفك</b>",
             f"المخاطر: {profile.risk_profile} | الأفق: {profile.horizon}",
             f"الإحاطة اليومية: {'مفعّلة ✅' if profile.daily_brief else 'متوقفة ⏸️'}"]
    if profile.capital_note:
        lines.append(f"ملاحظات: {html.escape(profile.capital_note)}")

    lines.append("\n<b>قائمة المتابعة</b>")
    lines.append("، ".join(watchlist) if watchlist else "— فاضية (أضف بـ /watch)")

    lines.append("\n<b>المحفظة</b>")
    if holdings:
        for h in holdings:
            avg = f" @ {h['avg_price']}" if h.get("avg_price") else ""
            lines.append(f"• {h['symbol']}: {h['quantity']}{avg}")
    else:
        lines.append("— فاضية (أضف بـ /add)")

    await _send(update, "\n".join(lines), ParseMode.HTML)


async def cmd_risk(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    profile = await _profile(update, context)
    choice = " ".join(context.args).strip()
    if choice not in RISK_PROFILES:
        await _send(update, "اختر واحداً من:\n" + "\n".join(f"/risk {r}" for r in RISK_PROFILES)
                    + f"\n\nالحالي: {profile.risk_profile}")
        return
    await _service(context).storage.update_profile(profile.user_id, risk_profile=choice)
    await _send(update, f"✅ مستوى المخاطر الآن: {choice}")


async def cmd_horizon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    profile = await _profile(update, context)
    choice = " ".join(context.args).strip()
    if choice not in HORIZONS:
        await _send(update, "اختر واحداً من:\n" + "\n".join(f"/horizon {h}" for h in HORIZONS)
                    + f"\n\nالحالي: {profile.horizon}")
        return
    await _service(context).storage.update_profile(profile.user_id, horizon=choice)
    await _send(update, f"✅ الأفق الزمني الآن: {choice}")


async def cmd_capital(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    profile = await _profile(update, context)
    note = " ".join(context.args).strip()
    if not note:
        await _send(update, "اكتب ملاحظتك بعد الأمر.\nمثال: /capital رأس مال 50 ألف درهم، بدون رافعة")
        return
    await _service(context).storage.update_profile(profile.user_id, capital_note=note)
    await _send(update, "✅ حفظت الملاحظة وسأراعيها في كل توصية.")


async def cmd_daily(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    profile = await _profile(update, context)
    arg = (context.args[0].lower() if context.args else "")
    if arg not in ("on", "off"):
        await _send(update, "الصيغة: /daily on أو /daily off\n"
                            f"الحالي: {'مفعّلة' if profile.daily_brief else 'متوقفة'}")
        return
    await _service(context).storage.update_profile(profile.user_id, daily_brief=(arg == "on"))
    when = f"{settings.brief_hour:02d}:{settings.brief_minute:02d} ({settings.timezone})"
    await _send(update, f"✅ الإحاطة اليومية {'مفعّلة، تصلك كل يوم ' + when if arg == 'on' else 'متوقفة'}.")


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    profile = await _profile(update, context)
    await _service(context).storage.clear_messages(profile.user_id)
    await _send(update, "🧹 مسحت ذاكرة المحادثة. ملفك ومحفظتك كما هي.")


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    question = (update.effective_message.text or "").strip()
    if not question:
        return
    profile = await _profile(update, context)
    placeholder = await _thinking(update, context, "🤔 أفكر وأتحقق من آخر المستجدات…")
    reply = await _service(context).chat(profile, question)
    await _deliver(update, placeholder, reply)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("خطأ أثناء معالجة التحديث", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "صار خطأ تقني أثناء التنفيذ. جرّب مرة أخرى بعد قليل، "
                "وإذا تكرر تحقّق من السجلات أو من رصيد مفتاح Claude."
            )
        except TelegramError:
            pass


# ── الإحاطة اليومية المجدولة ─────────────────────────────────
async def daily_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    service: AdvisorService = context.application.bot_data["service"]
    subscribers = await service.storage.subscribers()
    log.info("إرسال الإحاطة اليومية إلى %d مشترك", len(subscribers))
    for profile in subscribers:
        try:
            reply = await service.daily_brief(profile)
            for chunk in _chunks("🌅 إحاطة الصباح\n\n" + reply.formatted()):
                await context.bot.send_message(profile.user_id, chunk, disable_web_page_preview=True)
        except Exception as exc:
            log.warning("تعذّر إرسال الإحاطة إلى %s: %s", profile.user_id, exc)
        await asyncio.sleep(2)  # تفادي حدود معدّل تيليجرام


async def _post_init(app: Application) -> None:
    await app.bot.set_my_commands([
        BotCommand("brief", "إحاطة الأسواق الآن"),
        BotCommand("news", "آخر الأخبار وأثرها"),
        BotCommand("market", "أسعار مباشرة"),
        BotCommand("analyze", "تحليل أصل محدد"),
        BotCommand("portfolio", "مراجعة المحفظة"),
        BotCommand("add", "إضافة مركز للمحفظة"),
        BotCommand("watch", "إضافة لقائمة المتابعة"),
        BotCommand("list", "عرض الملف والمحفظة"),
        BotCommand("risk", "ضبط مستوى المخاطر"),
        BotCommand("daily", "تفعيل الإحاطة الصباحية"),
        BotCommand("help", "كل الأوامر"),
    ])


def build_application() -> Application:
    if not settings.telegram_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN غير موجود. احصل عليه من @BotFather وضعه في .env")

    storage = Storage(settings.db_path)
    service = AdvisorService(storage, AdvisorBrain())

    app = ApplicationBuilder().token(settings.telegram_token).post_init(_post_init).build()
    app.bot_data["service"] = service

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("brief", cmd_brief))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("market", cmd_market))
    app.add_handler(CommandHandler("analyze", cmd_analyze))
    app.add_handler(CommandHandler("portfolio", cmd_portfolio))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("watch", cmd_watch))
    app.add_handler(CommandHandler("unwatch", cmd_unwatch))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("risk", cmd_risk))
    app.add_handler(CommandHandler("horizon", cmd_horizon))
    app.add_handler(CommandHandler("capital", cmd_capital))
    app.add_handler(CommandHandler("daily", cmd_daily))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_error_handler(on_error)

    if app.job_queue is not None:
        app.job_queue.run_daily(
            daily_job,
            time=dtime(hour=settings.brief_hour, minute=settings.brief_minute,
                       tzinfo=ZoneInfo(settings.timezone)),
            name="daily_brief",
        )
    else:
        log.warning("JobQueue غير مثبّتة — الإحاطة اليومية معطّلة. ثبّت python-telegram-bot[job-queue]")

    return app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    app = build_application()
    log.info("بدأ تشغيل بوت المستشار المالي (الموديل: %s)", settings.model)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
