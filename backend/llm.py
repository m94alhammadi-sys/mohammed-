"""طبقة الاتصال بنموذج Claude.

مرحلتان منفصلتان عن قصد:
  1. `research()` — بحث مفتوح بأداة البحث الخادمية، مخرجه نص + استشهادات.
  2. `structure()` — تحويل نتيجة البحث إلى JSON مطابق للمخطط (Structured
     Outputs). فصل المرحلتين يتجنب تعارض الاستشهادات مع مخطط المخرجات،
     ويجعل الأدلة قابلة للتثبيت قبل صياغة الادعاء.

في غياب مفتاح API يعمل التطبيق بمزوّد محاكاة موسوم بوضوح (`degraded`)،
فلا يُعرض على المستخدم رأي مُختلق على أنه تحليل حقيقي.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .config import Settings, settings as default_settings
from .schemas import Evidence

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# أداة البحث الخادمية — تعمل على خوادم Anthropic بلا حلقة تنفيذ عندنا.
WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": 8,
}


class LLMError(RuntimeError):
    """فشل استدعاء النموذج بعد استنفاد المحاولات."""


@dataclass
class ResearchResult:
    text: str
    evidence: list[Evidence] = field(default_factory=list)
    used_web: bool = False
    degraded: bool = False
    stop_reason: str | None = None


class LLMClient:
    def __init__(self, cfg: Settings | None = None) -> None:
        self.cfg = cfg or default_settings
        self._client: Any = None
        if self.cfg.llm_enabled:
            import anthropic

            self._client = anthropic.AsyncAnthropic(api_key=self.cfg.anthropic_api_key)

    @property
    def enabled(self) -> bool:
        return self._client is not None

    # ------------------------------------------------------------- بحث

    async def research(
        self,
        system: str,
        prompt: str,
        *,
        model: str | None = None,
        effort: str = "high",
        allow_web: bool = True,
        allowed_domains: list[str] | None = None,
    ) -> ResearchResult:
        """جولة بحث حرة. يعيد النص الخام والاستشهادات المستخرجة."""
        if not self.enabled:
            return ResearchResult(
                text="[وضع العرض] لا يوجد اتصال بالنموذج ولا مصادر حية.",
                degraded=True,
            )

        tools: list[dict[str, Any]] = []
        if allow_web:
            tool = dict(WEB_SEARCH_TOOL)
            if allowed_domains:
                tool["allowed_domains"] = allowed_domains
            tools.append(tool)

        try:
            message = await self._client.messages.create(
                model=model or self.cfg.specialist_model,
                max_tokens=self.cfg.max_tokens,
                system=[{"type": "text", "text": system,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": prompt}],
                thinking={"type": "adaptive"},
                output_config={"effort": effort},
                tools=tools or None,
            )
        except Exception as exc:                                     # noqa: BLE001
            log.warning("فشل استدعاء البحث: %s", exc)
            return ResearchResult(text=f"تعذّر البحث الحي: {exc}", degraded=True)

        if message.stop_reason == "refusal":
            detail = getattr(message, "stop_details", None)
            reason = getattr(detail, "explanation", "") if detail else ""
            return ResearchResult(
                text=f"رفض النموذج تنفيذ الطلب. {reason}".strip(),
                degraded=True, stop_reason="refusal",
            )

        text_parts: list[str] = []
        evidence: list[Evidence] = []
        used_web = False

        for block in message.content:
            btype = getattr(block, "type", "")
            if btype == "text":
                text_parts.append(block.text)
            elif btype == "web_search_tool_result":
                used_web = True
                evidence.extend(self._evidence_from_search(block))

        return ResearchResult(
            text="\n".join(text_parts).strip(),
            evidence=evidence,
            used_web=used_web,
            stop_reason=message.stop_reason,
        )

    @staticmethod
    def _evidence_from_search(block: Any) -> list[Evidence]:
        """يستخرج الأدلة من كتلة نتيجة البحث.

        أخطاء أدوات الخادم تصل بحالة 200 ومحتواها كائن خطأ لا قائمة،
        لذا نفحص النوع قبل المرور على العناصر.
        """
        content = getattr(block, "content", None)
        if not isinstance(content, list):
            log.info("نتيجة بحث بحالة خطأ: %s", getattr(content, "error_code", content))
            return []

        out: list[Evidence] = []
        for item in content:
            if getattr(item, "type", "") != "web_search_result":
                continue
            url = getattr(item, "url", None)
            out.append(Evidence(
                source_type="web",
                title=getattr(item, "title", "") or (url or "مصدر بلا عنوان"),
                url=url,
                publisher=_domain_of(url),
                published_at=getattr(item, "page_age", None),
                reliability=_reliability_of(url),
            ))
        return out

    # ------------------------------------------------------------ هيكلة

    async def structure(
        self,
        system: str,
        prompt: str,
        schema_cls: type[T],
        *,
        model: str | None = None,
        effort: str = "high",
    ) -> T:
        """يحوّل نصاً إلى كائن مطابق للمخطط عبر Structured Outputs."""
        if not self.enabled:
            raise LLMError("النموذج غير مفعّل — استخدم المزوّد البديل")

        try:
            message = await self._client.messages.create(
                model=model or self.cfg.specialist_model,
                max_tokens=self.cfg.max_tokens,
                system=[{"type": "text", "text": system,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": prompt}],
                thinking={"type": "adaptive"},
                output_config={
                    "effort": effort,
                    "format": {
                        "type": "json_schema",
                        "schema": _strict_schema(schema_cls),
                    },
                },
            )
        except Exception as exc:                                     # noqa: BLE001
            raise LLMError(f"فشل طلب الهيكلة: {exc}") from exc

        if message.stop_reason == "refusal":
            raise LLMError("رفض النموذج إنتاج التقرير المطلوب")
        if message.stop_reason == "max_tokens":
            raise LLMError("انقطع المخرج قبل اكتماله (max_tokens)")

        raw = next((b.text for b in message.content if getattr(b, "type", "") == "text"), "")
        try:
            return schema_cls.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise LLMError(f"مخرج غير مطابق للمخطط: {exc}") from exc

    # ------------------------------------------------------------ دردشة

    async def chat(
        self,
        system: str,
        history: list[dict[str, str]],
        *,
        model: str | None = None,
        effort: str = "medium",
    ) -> str:
        """رد محادثة قصير — يُستخدم في الدردشة المباشرة مع وكيل واحد."""
        if not self.enabled:
            return ("[وضع العرض] النموذج غير مفعّل. أضف ANTHROPIC_API_KEY "
                    "في ملف .env لتشغيل التحليل الحقيقي.")
        try:
            message = await self._client.messages.create(
                model=model or self.cfg.specialist_model,
                max_tokens=4000,
                system=[{"type": "text", "text": system,
                         "cache_control": {"type": "ephemeral"}}],
                messages=history,
                thinking={"type": "adaptive"},
                output_config={"effort": effort},
            )
        except Exception as exc:                                     # noqa: BLE001
            log.warning("فشل الرد الحواري: %s", exc)
            return f"تعذّر الرد الآن: {exc}"

        if message.stop_reason == "refusal":
            return "تعذّر الرد على هذا الطلب."
        return "\n".join(
            b.text for b in message.content if getattr(b, "type", "") == "text"
        ).strip()


# ------------------------------------------------------------ أدوات مساعدة

def _strict_schema(model_cls: type[BaseModel]) -> dict[str, Any]:
    """يحوّل مخطط Pydantic إلى مخطط صارم يقبله الـ API.

    المطلوب: `additionalProperties: false` وكل الخصائص في `required`،
    في المخطط الجذر وفي كل تعريف فرعي داخل `$defs`.
    """
    schema = model_cls.model_json_schema()

    def _harden(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            for value in node.values():
                _harden(value)
        elif isinstance(node, list):
            for value in node:
                _harden(value)

    _harden(schema)
    return schema


def _domain_of(url: str | None) -> str | None:
    if not url:
        return None
    try:
        from urllib.parse import urlparse

        return urlparse(url).netloc or None
    except ValueError:
        return None


# موثوقية تقديرية حسب نوع النطاق — تُستخدم في ترجيح الأدلة لا في إخفائها.
_HIGH_TRUST_SUFFIXES = (".gov", ".gov.uk", ".europa.eu", ".int", ".edu")
_HIGH_TRUST_HOSTS = {
    "federalreserve.gov", "ecb.europa.eu", "imf.org", "worldbank.org", "bis.org",
    "oecd.org", "sec.gov", "eia.gov", "bls.gov", "opec.org", "un.org",
    "reuters.com", "apnews.com", "bloomberg.com", "ft.com", "wsj.com",
}
_LOW_TRUST_HOSTS = {"t.me", "x.com", "twitter.com", "facebook.com", "tiktok.com"}


def _reliability_of(url: str | None) -> float:
    host = (_domain_of(url) or "").lower().removeprefix("www.")
    if not host:
        return 0.4
    if host in _HIGH_TRUST_HOSTS or host.endswith(_HIGH_TRUST_SUFFIXES):
        return 0.9
    if host in _LOW_TRUST_HOSTS:
        return 0.35
    return 0.6


llm = LLMClient()
