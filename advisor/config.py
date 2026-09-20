"""إعدادات التطبيق، تُقرأ من متغيرات البيئة أو ملف .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _id_set(name: str) -> set[int]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return set()
    out: set[int] = set()
    for part in raw.replace(" ", "").split(","):
        if part:
            try:
                out.add(int(part))
            except ValueError:
                continue
    return out


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

    model: str = os.getenv("ADVISOR_MODEL", "claude-opus-5")
    effort: str = os.getenv("ADVISOR_EFFORT", "high")
    max_tokens: int = _int_env("ADVISOR_MAX_TOKENS", 32000)

    timezone: str = os.getenv("ADVISOR_TIMEZONE", "Asia/Dubai")
    brief_hour: int = _int_env("ADVISOR_BRIEF_HOUR", 8)
    brief_minute: int = _int_env("ADVISOR_BRIEF_MINUTE", 0)

    db_path: str = os.getenv("ADVISOR_DB_PATH", "advisor_data.sqlite3")
    allowed_user_ids: frozenset[int] = field(
        default_factory=lambda: frozenset(_id_set("ADVISOR_ALLOWED_USER_IDS"))
    )

    # عدد الرسائل المحفوظة في ذاكرة المحادثة لكل مستخدم
    history_turns: int = _int_env("ADVISOR_HISTORY_TURNS", 12)

    # واتساب (اختياري)
    whatsapp_token: str = os.getenv("WHATSAPP_TOKEN", "")
    whatsapp_phone_number_id: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    whatsapp_verify_token: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "")

    def is_allowed(self, user_id: int) -> bool:
        """قائمة فاضية = البوت مفتوح للجميع."""
        return not self.allowed_user_ids or user_id in self.allowed_user_ids


settings = Settings()
