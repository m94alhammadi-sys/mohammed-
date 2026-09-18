"""جدولة المهام الدورية — المسح، الموجزات، التذكيرات."""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .config import settings
from .scanner import (
    check_price_alerts,
    fire_reminders,
    scan_news_shocks,
    scan_opportunities,
    send_brief,
)

log = logging.getLogger(__name__)

_SCHEDULER: BackgroundScheduler | None = None


def _guard(name: str, func):
    """يغلّف المهمة حتى لا يُسقط خطأٌ واحد الجدولة كلها."""

    def wrapped():
        try:
            result = func()
            if result:
                log.info("المهمة «%s» أنجزت: %s", name, result)
            else:
                log.debug("المهمة «%s» لم تنتج شيئاً", name)
        except Exception:
            log.exception("فشلت المهمة «%s»", name)

    wrapped.__name__ = f"job_{name}"
    return wrapped


def start_scheduler() -> BackgroundScheduler:
    """يشغّل كل المهام الدورية."""
    global _SCHEDULER
    if _SCHEDULER and _SCHEDULER.running:
        return _SCHEDULER

    scheduler = BackgroundScheduler(
        timezone=settings.timezone,
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
    )

    # 1) التذكيرات — كل دقيقة (رخيصة، لا تنادي النموذج)
    scheduler.add_job(
        _guard("التذكيرات", fire_reminders),
        IntervalTrigger(minutes=1),
        id="reminders",
    )

    # 2) التنبيهات السعرية — كل 5 دقائق
    scheduler.add_job(
        _guard("التنبيهات السعرية", check_price_alerts),
        IntervalTrigger(minutes=5),
        id="price_alerts",
    )

    # 3) مسح الفرص الفنية
    scheduler.add_job(
        _guard("مسح الفرص", scan_opportunities),
        IntervalTrigger(minutes=settings.scan_interval_minutes),
        id="opportunities",
    )

    # 4) مسح الصدمات الإخبارية — كل نصف ساعة
    scheduler.add_job(
        _guard("مسح الأخبار", scan_news_shocks),
        IntervalTrigger(minutes=30),
        id="news_shocks",
    )

    # 5) الموجز الصباحي — أيام العمل فقط
    morning = settings.morning_brief_time
    scheduler.add_job(
        _guard("الموجز الصباحي", lambda: send_brief("morning")),
        CronTrigger(day_of_week="mon-fri", hour=morning.hour, minute=morning.minute),
        id="morning_brief",
    )

    # 6) ملخص الإغلاق
    evening = settings.evening_brief_time
    scheduler.add_job(
        _guard("ملخص الإغلاق", lambda: send_brief("evening")),
        CronTrigger(day_of_week="mon-fri", hour=evening.hour, minute=evening.minute),
        id="evening_brief",
    )

    scheduler.start()
    _SCHEDULER = scheduler
    log.info(
        "الجدولة تعمل بتوقيت %s | مسح كل %s دقيقة | موجز %s و %s",
        settings.timezone,
        settings.scan_interval_minutes,
        morning.strftime("%H:%M"),
        evening.strftime("%H:%M"),
    )
    return scheduler


def stop_scheduler() -> None:
    global _SCHEDULER
    if _SCHEDULER and _SCHEDULER.running:
        _SCHEDULER.shutdown(wait=False)
        log.info("تم إيقاف الجدولة")
    _SCHEDULER = None


def job_status() -> list[dict]:
    """حالة المهام — تظهر في /health."""
    if not _SCHEDULER:
        return []
    return [
        {
            "المهمة": job.id,
            "التشغيل_القادم": str(job.next_run_time) if job.next_run_time else "متوقفة",
        }
        for job in _SCHEDULER.get_jobs()
    ]
