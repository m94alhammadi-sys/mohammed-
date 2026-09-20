"""نواة الذكاء: استدعاء Claude مع أدوات البحث والجلب من الإنترنت.

الاتصال بالإنترنت يتم عبر أدوات الخادم من Anthropic (web_search / web_fetch)
التي تعمل على خوادم Anthropic — لا تحتاج مفاتيح مزوّدي أخبار.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import anthropic

from .config import settings
from .prompts import DISCLAIMER, system_prompt

log = logging.getLogger(__name__)

# أدوات الخادم: البحث في الويب وجلب صفحة محددة.
WEB_TOOLS: list[dict] = [
    {
        "type": "web_search_20260209",
        "name": "web_search",
        "max_uses": 8,
    },
    {
        "type": "web_fetch_20260209",
        "name": "web_fetch",
        "max_uses": 5,
        "citations": {"enabled": True},
        "max_content_tokens": 40000,
    },
]

# الرجوع التلقائي لموديل آخر إذا رفض الموديل الأساسي الطلب.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

MAX_PAUSE_RESTARTS = 5

REFUSAL_REPLY = (
    "تعذّر عليّ معالجة هذا الطلب بصيغته الحالية. جرّب تصيغه بشكل مختلف أو اسألني عن "
    "الجانب التحليلي منه."
)


@dataclass
class AdvisorReply:
    text: str
    sources: list[str] = field(default_factory=list)
    searched: int = 0
    stop_reason: str = ""
    usage: dict[str, int] = field(default_factory=dict)

    def formatted(self) -> str:
        """النص النهائي مع المصادر وسطر التنويه."""
        out = self.text.strip() or "لم أتمكن من توليد رد. حاول مرة أخرى."
        if self.sources:
            uniq = list(dict.fromkeys(self.sources))[:6]
            out += "\n\n🔎 مصادر: " + " • ".join(uniq)
        if DISCLAIMER not in out:
            out += f"\n\n{DISCLAIMER}"
        return out


class AdvisorBrain:
    """غلاف رقيق حول Claude يضيف: أدوات الويب، التخزين المؤقت، ومعالجة pause_turn."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        key = api_key or settings.anthropic_api_key
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY غير موجود. ضعه في ملف .env قبل تشغيل البوت."
            )
        self._client = anthropic.AsyncAnthropic(api_key=key, max_retries=3)
        self._model = model or settings.model
        self._use_fallbacks = True  # يُطفأ تلقائياً إذا لم يدعمه الحساب

    async def ask(
        self,
        user_turn: str,
        history: list[dict[str, str]] | None = None,
        *,
        max_tokens: int | None = None,
        effort: str | None = None,
    ) -> AdvisorReply:
        """سؤال واحد → رد كامل، مع بحث حيّ في الإنترنت عند الحاجة."""
        messages: list[dict] = []
        for item in history or []:
            if item.get("role") in ("user", "assistant") and item.get("content"):
                messages.append({"role": item["role"], "content": item["content"]})
        messages.append({"role": "user", "content": user_turn})

        sources: list[str] = []
        searched = 0
        texts: list[str] = []
        usage: dict[str, int] = {}
        stop_reason = ""

        for attempt in range(MAX_PAUSE_RESTARTS + 1):
            message = await self._create(messages, max_tokens=max_tokens, effort=effort)
            stop_reason = message.stop_reason or ""
            usage = _merge_usage(usage, message.usage)

            if stop_reason == "refusal":
                return AdvisorReply(text=REFUSAL_REPLY, stop_reason=stop_reason, usage=usage)

            found, hits = _collect_sources(message.content)
            sources.extend(found)
            searched += hits
            texts.extend(b.text for b in message.content if getattr(b, "type", "") == "text")

            if stop_reason != "pause_turn":
                break

            # الدور توقّف مؤقتاً أثناء عمل أداة خادم — نكمله بإعادة إرساله.
            messages.append({"role": "assistant", "content": message.content})
            if attempt == MAX_PAUSE_RESTARTS:
                log.warning("تجاوز عدد محاولات استئناف pause_turn الحد الأقصى")

        return AdvisorReply(
            text="\n".join(t for t in texts if t.strip()),
            sources=sources,
            searched=searched,
            stop_reason=stop_reason,
            usage=usage,
        )

    async def _create(self, messages: list[dict], *, max_tokens: int | None, effort: str | None):
        """طلب واحد للـ API، مع بث متدفق لتفادي مهلة الاتصال في الردود الطويلة."""
        params = {
            "model": self._model,
            "max_tokens": max_tokens or settings.max_tokens,
            "system": [
                {
                    "type": "text",
                    "text": system_prompt(),
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": messages,
            "tools": WEB_TOOLS,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort or settings.effort},
        }

        if self._use_fallbacks:
            try:
                async with self._client.beta.messages.stream(
                    **params, betas=[FALLBACK_BETA], fallbacks="default"
                ) as stream:
                    return await stream.get_final_message()
            except anthropic.BadRequestError as exc:
                if not _is_unsupported_fallback(exc):
                    raise
                log.info("تعطيل الرجوع التلقائي للموديل البديل (غير مدعوم لهذا الحساب): %s", exc)
                self._use_fallbacks = False

        async with self._client.messages.stream(**params) as stream:
            return await stream.get_final_message()


def _is_unsupported_fallback(exc: anthropic.BadRequestError) -> bool:
    blob = str(exc).lower()
    return "fallback" in blob or "beta" in blob


def _collect_sources(content) -> tuple[list[str], int]:
    """يستخرج عناوين نتائج البحث ليعرضها البوت كمصادر."""
    sources: list[str] = []
    hits = 0
    for block in content:
        btype = getattr(block, "type", "")
        if btype == "web_search_tool_result":
            results = getattr(block, "content", None)
            if isinstance(results, list):
                hits += 1
                for item in results:
                    title = getattr(item, "title", None)
                    url = getattr(item, "url", "")
                    label = title or url
                    if label:
                        sources.append(_short_source(label, url))
        elif btype == "web_fetch_tool_result":
            result = getattr(block, "content", None)
            url = getattr(result, "url", "")
            if url:
                sources.append(_short_source(url, url))
    return sources, hits


def _short_source(label: str, url: str) -> str:
    label = (label or "").strip()
    if len(label) > 60:
        label = label[:57] + "…"
    domain = ""
    if url:
        part = url.split("//", 1)[-1].split("/", 1)[0]
        domain = part.replace("www.", "")
    return f"{label} ({domain})" if domain and domain not in label else label


def _merge_usage(acc: dict[str, int], usage) -> dict[str, int]:
    for key in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
        value = getattr(usage, key, None)
        if isinstance(value, int):
            acc[key] = acc.get(key, 0) + value
    return acc
