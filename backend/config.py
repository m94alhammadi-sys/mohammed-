"""إعدادات التطبيق - تُقرأ من متغيرات البيئة (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """محمّل .env بسيط بدون اعتماديات خارجية."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    # --- النماذج ---
    # نموذج الوكلاء المتخصصين ونموذج الوكيل التنسيقي.
    specialist_model: str = os.environ.get("SPECIALIST_MODEL", "claude-opus-5")
    chief_model: str = os.environ.get("CHIEF_MODEL", "claude-opus-5")
    # مستوى الجهد: low | medium | high | xhigh | max
    specialist_effort: str = os.environ.get("SPECIALIST_EFFORT", "high")
    chief_effort: str = os.environ.get("CHIEF_EFFORT", "xhigh")
    max_tokens: int = _env_int("MAX_TOKENS", 16000)

    # --- المفاتيح ---
    anthropic_api_key: str | None = os.environ.get("ANTHROPIC_API_KEY")
    # مفاتيح اختيارية لمصادر البيانات؛ غيابها لا يُعطّل التطبيق.
    fred_api_key: str | None = os.environ.get("FRED_API_KEY")
    x_bearer_token: str | None = os.environ.get("X_BEARER_TOKEN")
    youtube_api_key: str | None = os.environ.get("YOUTUBE_API_KEY")
    newsapi_key: str | None = os.environ.get("NEWSAPI_KEY")
    finnhub_api_key: str | None = os.environ.get("FINNHUB_API_KEY")

    # --- التشغيل ---
    host: str = os.environ.get("HOST", "127.0.0.1")
    port: int = _env_int("PORT", 8000)
    db_path: Path = field(default_factory=lambda: BASE_DIR / os.environ.get("DB_PATH", "majlis.db"))
    # وضع العرض: يعمل بدون مفتاح Anthropic بردود محاكاة واضحة الوسم.
    offline_demo: bool = _env_bool("OFFLINE_DEMO", False)
    # مهلة الوكيل الواحد بالثواني داخل دورة التنسيق.
    agent_timeout_s: int = _env_int("AGENT_TIMEOUT_S", 240)
    # عدد المصادر التي يجلبها كل موصل بيانات.
    max_evidence_per_tool: int = _env_int("MAX_EVIDENCE_PER_TOOL", 6)
    http_timeout_s: int = _env_int("HTTP_TIMEOUT_S", 15)

    @property
    def llm_enabled(self) -> bool:
        """هل يمكن الاتصال فعلياً بنموذج Claude؟"""
        return bool(self.anthropic_api_key) and not self.offline_demo


settings = Settings()
