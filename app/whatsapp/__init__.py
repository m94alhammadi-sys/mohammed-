"""تكامل واتساب — يدعم Meta Cloud API و Twilio."""

from __future__ import annotations

import logging

from ..config import settings
from .base import InboundMessage, WhatsAppProvider
from .meta import MetaProvider
from .twilio_provider import TwilioProvider

log = logging.getLogger(__name__)

_PROVIDER: WhatsAppProvider | None = None


def get_provider() -> WhatsAppProvider:
    """يعيد مزوّد واتساب المفعّل (نمط Singleton)."""
    global _PROVIDER
    if _PROVIDER is None:
        if settings.provider == "twilio":
            _PROVIDER = TwilioProvider()
        else:
            _PROVIDER = MetaProvider()
        log.info("مزوّد واتساب المفعّل: %s", _PROVIDER.name)
    return _PROVIDER


__all__ = ["InboundMessage", "WhatsAppProvider", "MetaProvider", "TwilioProvider", "get_provider"]
