"""الماسح الاستباقي — يبحث عن الفرص ويقرر متى يستحق الأمر إزعاج المستخدم."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from . import db
from .brain import run_task
from .config import settings
from .market.analysis import analyze
from .market.data import get_quote
from .market.symbols import describe
from .notify import notify
from .prompts import ALERT_TASK, EVENING_BRIEF_TASK, MORNING_BRIEF_TASK, NEWS_SHOCK_TASK

log = logging.getLogger(__name__)

# الرموز التي تُراقَب دائماً حتى لو كانت قائمة المتابعة فارغة
CORE_SYMBOLS = ["^GSPC", "^IXIC", "GC=F", "CL=F", "EURUSD=X", "DX-Y.NYB", "BTC-USD"]

IGNORE_TOKEN = "تجاهل"


def _signal_kind(analysis) -> str:
    """مفتاح لتمييز نوع الإشارة — يمنع تكرار نفس التنبيه."""
    if not analysis.signals:
        return analysis.bias
    strongest = max(analysis.signals, key=lambda s: s.weight)
    return f"{analysis.bias}:{strongest.name}"


def _is_opportunity(analysis) -> bool:
    """هل درجة القوة متطرفة كفاية لتستحق النظر؟"""
    high = settings.alert_min_score
    low = 100 - high
    return analysis.score >= high or analysis.score <= low


def _watch_symbols(phone: str) -> list[str]:
    symbols = [r["symbol"] for r in db.get_watchlist(phone)]
    if phone == settings.owner_number:
        symbols += [s for s in CORE_SYMBOLS if s not in symbols]
    return symbols


# ------------------------------------------------------------ فحص الفرص الفنية


def scan_opportunities() -> int:
    """يفحص قوائم المتابعة ويرسل تنبيهاً عند وجود فرصة مؤكدة. يعيد عدد التنبيهات."""
    sent = 0
    for user in db.all_users(only_alerts=True):
        phone = user["phone"]

        if db.alerts_sent_today(phone) >= settings.max_alerts_per_day:
            log.info("بلغ %s سقف التنبيهات اليومي", phone)
            continue

        for symbol in _watch_symbols(phone):
            try:
                analysis = analyze(symbol)
            except Exception as exc:
                log.debug("تخطي %s أثناء المسح: %s", symbol, exc)
                continue

            if not _is_opportunity(analysis):
                continue

            kind = _signal_kind(analysis)
            if db.alert_on_cooldown(phone, symbol, kind, settings.alert_cooldown_hours):
                continue

            payload = analysis.to_dict()
            signal_block = json.dumps(
                {
                    "الرمز": payload["الرمز"],
                    "الاسم": payload["الاسم"],
                    "السعر": payload["السعر"],
                    "درجة_القوة": payload["درجة_القوة"],
                    "الانحياز": payload["الانحياز"],
                    "الإشارات": payload["الإشارات"],
                    "المستويات": payload["المستويات"],
                    "سيناريو_مقترح": payload["سيناريو_مقترح"],
                },
                ensure_ascii=False,
            )

            try:
                reply = run_task(phone, ALERT_TASK.format(signal_block=signal_block), user["name"])
            except Exception as exc:
                log.exception("فشل توليد تنبيه لـ %s: %s", symbol, exc)
                continue

            # النموذج هو الفلتر الأخير — يرفض الإشارات الضعيفة
            if reply.strip().startswith(IGNORE_TOKEN):
                log.info("رفض النموذج إشارة %s لـ %s", kind, symbol)
                db.record_alert(phone, symbol, kind, analysis.score, {"مرفوض": True})
                continue

            if notify(phone, reply):
                db.record_alert(phone, symbol, kind, analysis.score, payload["سيناريو_مقترح"])
                sent += 1
                log.info("أُرسل تنبيه %s لـ %s", kind, symbol)

            if db.alerts_sent_today(phone) >= settings.max_alerts_per_day:
                break

    return sent


# ------------------------------------------------------------- التنبيهات السعرية


def check_price_alerts() -> int:
    """يفحص التنبيهات السعرية المحددة يدوياً من المستخدم."""
    fired = 0
    cache: dict[str, float] = {}

    for alert in db.active_price_alerts():
        symbol = alert["symbol"]
        if symbol not in cache:
            try:
                cache[symbol] = get_quote(symbol).price
            except Exception as exc:
                log.debug("تعذّر جلب سعر %s للتنبيه: %s", symbol, exc)
                continue

        price = cache[symbol]
        target = float(alert["price"])
        hit = price >= target if alert["direction"] == "above" else price <= target
        if not hit:
            continue

        arrow = "📈 اخترق" if alert["direction"] == "above" else "📉 نزل تحت"
        message = (
            f"🔔 *تنبيه سعري*\n\n"
            f"{describe(symbol)} {arrow} مستوى {target}\n"
            f"السعر الآن: *{round(price, 4)}*"
        )
        if alert["note"]:
            message += f"\n\nملاحظتك: {alert['note']}"

        if notify(alert["phone"], message):
            db.fire_price_alert(alert["id"])
            fired += 1

    return fired


# ------------------------------------------------------------ الصدمات الإخبارية


def _news_fingerprint(items: list[dict]) -> str:
    blob = "|".join(sorted(i.get("العنوان", "") for i in items))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def scan_news_shocks() -> int:
    """يرصد الأخبار عالية التأثير ويقيّم أثرها قبل الإرسال."""
    from .market import news as news_mod

    try:
        items = news_mod.breaking_risk_scan(limit=6)
    except Exception as exc:
        log.warning("فشل مسح الأخبار: %s", exc)
        return 0

    if not items:
        return 0

    fingerprint = _news_fingerprint(items)
    with db.tx() as conn:
        row = conn.execute("SELECT value FROM kv WHERE key = 'last_news_fingerprint'").fetchone()
        if row and row["value"] == fingerprint:
            return 0                                  # نفس الأخبار — لا تكرر
        conn.execute(
            "INSERT INTO kv (key, value, updated_at) VALUES ('last_news_fingerprint', ?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (fingerprint, db.iso(db.now_utc())),
        )

    news_block = json.dumps(items, ensure_ascii=False, indent=1)
    sent = 0
    for user in db.all_users(only_alerts=True):
        phone = user["phone"]
        if db.alerts_sent_today(phone) >= settings.max_alerts_per_day:
            continue
        try:
            reply = run_task(phone, NEWS_SHOCK_TASK.format(news_block=news_block), user["name"])
        except Exception as exc:
            log.exception("فشل تقييم الصدمة الإخبارية: %s", exc)
            continue

        if reply.strip().startswith(IGNORE_TOKEN):
            continue
        if notify(phone, reply):
            db.record_alert(phone, "NEWS", "صدمة إخبارية", 0.0, {"بصمة": fingerprint})
            sent += 1

    return sent


# -------------------------------------------------------------------- الموجزات


def send_brief(kind: str = "morning") -> int:
    """الموجز الصباحي أو المسائي لكل المشتركين."""
    task = MORNING_BRIEF_TASK if kind == "morning" else EVENING_BRIEF_TASK
    sent = 0
    for user in db.all_users(only_brief=True):
        try:
            reply = run_task(user["phone"], task, user["name"])
        except Exception as exc:
            log.exception("فشل توليد الموجز (%s) لـ %s: %s", kind, user["phone"], exc)
            continue
        if notify(user["phone"], reply):
            sent += 1
    return sent


# ------------------------------------------------------------------ التذكيرات


def fire_reminders() -> int:
    """يرسل التذكيرات المستحقة (لمرة واحدة واليومية)."""
    fired = 0
    tz = ZoneInfo(settings.timezone)
    now_local = datetime.now(tz)

    for reminder in db.due_reminders():
        if notify(reminder["phone"], f"⏰ *تذكير*\n\n{reminder['text']}"):
            db.complete_reminder(reminder["id"])
            fired += 1

    for reminder in db.daily_reminders(now_local.strftime("%H:%M")):
        last = db.parse_iso(reminder["last_fired_at"])
        if last and last.astimezone(tz).date() == now_local.date():
            continue                                   # أُرسل اليوم بالفعل
        if notify(reminder["phone"], f"⏰ *تذكير يومي*\n\n{reminder['text']}"):
            db.complete_reminder(reminder["id"], keep_active=True)
            fired += 1

    return fired
