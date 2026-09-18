"""تحميل الإعدادات من متغيرات البيئة (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import time as dtime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, "").strip() or default)
    except ValueError:
        return default


def _csv(key: str) -> list[str]:
    raw = os.getenv(key, "").strip()
    if not raw:
        return []
    return [normalize_phone(p) for p in raw.split(",") if p.strip()]


def _hhmm(key: str, default: str) -> dtime:
    raw = (os.getenv(key, "").strip() or default).replace(".", ":")
    try:
        hh, mm = raw.split(":")[:2]
        return dtime(int(hh), int(mm))
    except (ValueError, IndexError):
        hh, mm = default.split(":")
        return dtime(int(hh), int(mm))


def normalize_phone(phone: str) -> str:
    """توحيد صيغة الرقم: أرقام فقط بدون + أو مسافات."""
    return "".join(ch for ch in str(phone) if ch.isdigit())


@dataclass(frozen=True)
class Settings:
    # --- Claude ---
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    model: str = os.getenv("CLAUDE_MODEL", "claude-opus-5")
    effort: str = os.getenv("CLAUDE_EFFORT", "high")
    enable_refusal_fallback: bool = _bool("ENABLE_REFUSAL_FALLBACK", True)
    web_search_max_uses: int = _int("WEB_SEARCH_MAX_USES", 8)

    # --- WhatsApp ---
    provider: str = os.getenv("WHATSAPP_PROVIDER", "meta").strip().lower()
    meta_access_token: str = os.getenv("META_ACCESS_TOKEN", "")
    meta_phone_number_id: str = os.getenv("META_PHONE_NUMBER_ID", "")
    meta_verify_token: str = os.getenv("META_VERIFY_TOKEN", "")
    meta_alert_template: str = os.getenv("META_ALERT_TEMPLATE", "market_alert")
    meta_template_lang: str = os.getenv("META_TEMPLATE_LANG", "ar")
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_whatsapp_from: str = os.getenv("TWILIO_WHATSAPP_FROM", "")

    # --- الأمان ---
    allowed_numbers: list[str] = field(default_factory=lambda: _csv("ALLOWED_NUMBERS"))
    owner_number: str = normalize_phone(os.getenv("OWNER_NUMBER", ""))

    # --- الجدولة ---
    timezone: str = os.getenv("TZ", "Asia/Dubai")
    scan_interval_minutes: int = _int("SCAN_INTERVAL_MINUTES", 15)
    morning_brief_time: dtime = field(default_factory=lambda: _hhmm("MORNING_BRIEF_TIME", "07:30"))
    evening_brief_time: dtime = field(default_factory=lambda: _hhmm("EVENING_BRIEF_TIME", "18:30"))
    alert_min_score: int = _int("ALERT_MIN_SCORE", 68)
    alert_cooldown_hours: int = _int("ALERT_COOLDOWN_HOURS", 6)
    max_alerts_per_day: int = _int("MAX_ALERTS_PER_DAY", 12)

    # --- التخزين ---
    db_path: str = os.getenv("DB_PATH", "data/agent.db")
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    port: int = _int("PORT", 8000)

    def is_allowed(self, phone: str) -> bool:
        """هل يُسمح لهذا الرقم بالتحدث مع الوكيل؟"""
        if not self.allowed_numbers:
            return True
        return normalize_phone(phone) in self.allowed_numbers

    @property
    def db_file(self) -> Path:
        path = Path(self.db_path)
        if not path.is_absolute():
            path = BASE_DIR / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
