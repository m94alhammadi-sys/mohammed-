"""سجل الموصلات: أي وكيل يقرأ من أي مصدر.

هذا الجدول هو حدود صلاحيات القراءة: وكيل المشاعر لا يصل إلى بيانات
الفائدة، ووكيل الاقتصاد لا يقرأ منشورات Reddit. فصل المصادر يفرض فصل
الاختصاص على مستوى البنية لا على مستوى النصيحة فقط.

يضيف هذا الملف أيضاً **فحص صحة المصادر** (`probe_sources`): يخبر
المستخدم بالضبط أي مصدر يعمل على جهازه وأيها يحتاج مفتاحاً وأيها
محجوب — بدل أن يكتشف ذلك من فجوات متفرقة داخل التقارير.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from ..schemas import AgentId
from .base import ConnectorResult, FailureKind
from .macro import fetch_macro_series, fetch_worldbank
from .market import fetch_market_snapshot
from .news import fetch_news, search_google_news
from .social import fetch_social_pulse, fetch_x_pulse, fetch_youtube_pulse

Fetcher = Callable[[str], Awaitable[ConnectorResult]]


def _category(name: str, category: str) -> Fetcher:
    """يثبّت مجال الخلاصات ويحتفظ باسم مقروء في التتبّع."""
    async def fetcher(topic: str) -> ConnectorResult:
        return await fetch_news(topic, category)

    fetcher.__name__ = name
    return fetcher


async def _market(_: str) -> ConnectorResult:
    return await fetch_market_snapshot()


async def _macro_series(_: str) -> ConnectorResult:
    return await fetch_macro_series()


async def _worldbank(_: str) -> ConnectorResult:
    return await fetch_worldbank()


CONNECTORS: dict[AgentId, list[Fetcher]] = {
    AgentId.SOCIAL: [fetch_social_pulse, fetch_x_pulse, fetch_youtube_pulse],
    AgentId.GEO: [_category("news_geo", "geo"), search_google_news],
    AgentId.MACRO: [_category("news_macro", "macro"), _macro_series, _worldbank],
    AgentId.BREAKING: [_category("news_breaking", "breaking"), search_google_news],
    AgentId.FLOW: [_market, _category("news_markets", "markets")],
}


async def gather_context(agent_id: AgentId, topic: str) -> list[ConnectorResult]:
    """يشغّل كل موصلات الوكيل بالتوازي ويعيد النتائج ناجحها وفاشلها.

    النتائج الفاشلة تُعاد عمداً: الوكيل يحتاج أن يعرف أنه أعمى في مصدر
    ما ليعلنه في `data_gaps`.
    """
    fetchers = CONNECTORS.get(agent_id, [])
    if not fetchers:
        return []
    results = await asyncio.gather(
        *(fetcher(topic) for fetcher in fetchers), return_exceptions=True
    )
    out: list[ConnectorResult] = []
    for fetcher, result in zip(fetchers, results):
        if isinstance(result, BaseException):
            out.append(ConnectorResult.failed(
                getattr(fetcher, "__name__", "connector"),
                f"استثناء: {result}", FailureKind.MALFORMED,
            ))
        else:
            out.append(result)
    return out


def coverage(results: list[ConnectorResult]) -> dict[str, object]:
    """ملخص تغطية المصادر لدورة وكيل واحد.

    التمييز الجوهري: **العمى الكامل** (`blind`) يعني لا دليل واحد وصل،
    وهو وحده ما يستوجب رفع `degraded`. أما مفتاح ناقص مع بقاء مصادر
    أخرى حية فهو نقص تغطية يُعلَن ولا يُسقط التقرير.
    """
    ok = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]
    return {
        "total": len(results),
        "ok": len(ok),
        "evidence": sum(len(r.evidence) for r in ok),
        "blind": not ok,
        "missing_keys": [r.name for r in failed if r.kind and r.kind.is_config_gap],
        "outages": [r.name for r in failed if r.kind and r.kind.is_outage],
        "empty": [r.name for r in failed
                  if r.kind is FailureKind.EMPTY or r.kind is FailureKind.MALFORMED],
    }


# ------------------------------------------------------------ فحص الصحة

# مصدر تمثيلي لكل موصل، يُفحص بموضوع محايد
_PROBE_TOPIC = "inflation"


async def probe_sources() -> list[dict[str, object]]:
    """يفحص كل موصل مرة واحدة ويصف حالته بلغة مفهومة.

    يُستخدم من `GET /api/sources` ليعرف المستخدم ما يعمل على جهازه فعلاً
    قبل أن يبني قراراً على تقرير ناقص.
    """
    seen: dict[str, tuple[AgentId, Fetcher]] = {}
    for agent_id, fetchers in CONNECTORS.items():
        for fetcher in fetchers:
            key = getattr(fetcher, "__name__", repr(fetcher))
            seen.setdefault(key, (agent_id, fetcher))

    async def run(agent_id: AgentId, fetcher: Fetcher) -> dict[str, object]:
        try:
            result = await fetcher(_PROBE_TOPIC)
        except Exception as exc:                                  # noqa: BLE001
            return {"agent": agent_id.value, "source": getattr(fetcher, "__name__", "?"),
                    "ok": False, "state": "خطأ", "detail": str(exc)[:160],
                    "evidence": 0, "actionable": False}

        state = "يعمل" if result.ok else (result.kind.label if result.kind else "غير متاح")
        return {
            "agent": agent_id.value,
            "source": result.name,
            "ok": result.ok,
            "state": state,
            "detail": result.note,
            "evidence": len(result.evidence),
            # هل يستطيع المستخدم إصلاحه بنفسه (بإضافة مفتاح)؟
            "actionable": bool(result.kind and result.kind.is_config_gap),
        }

    return list(await asyncio.gather(*(run(a, f) for a, f in seen.values())))
