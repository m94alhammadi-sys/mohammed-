"""إرسال الرسائل الاستباقية مع احترام نافذة الـ 24 ساعة في واتساب."""

from __future__ import annotations

import logging

from . import db
from .config import settings
from .whatsapp import get_provider

log = logging.getLogger(__name__)


def notify(phone: str, text: str) -> bool:
    """يرسل رسالة للمستخدم.

    واتساب يمنع الرسائل الحرة بعد مرور 24 ساعة على آخر رسالة من المستخدم، لذلك
    نتحول تلقائياً إلى قالب معتمد خارج النافذة.
    """
    if not text or not text.strip():
        return False

    provider = get_provider()
    in_window = db.within_service_window(phone)
    template = settings.meta_alert_template if settings.provider == "meta" else None

    if not in_window and not template:
        log.warning("خارج نافذة الـ 24 ساعة ولا يوجد قالب معتمد — لم تُرسل الرسالة لـ %s", phone)
        return False

    try:
        ids = provider.send(phone, text, in_window=in_window, template=template)
    except Exception as exc:
        log.exception("فشل الإرسال إلى %s: %s", phone, exc)
        return False

    if not ids:
        log.error("لم يقبل المزوّد الرسالة الموجهة إلى %s", phone)
        return False

    if not in_window:
        log.info("أُرسل قالب لـ %s (خارج نافذة الـ 24 ساعة)", phone)
    return True
