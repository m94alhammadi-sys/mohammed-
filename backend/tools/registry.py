"""سجل الموصلات: أي وكيل يقرأ من أي مصدر.

هذا الجدول هو حدود صلاحيات القراءة: وكيل المشاعر لا يصل إلى بيانات
الفائدة، ووكيل الاقتصاد لا يقرأ منشورات Reddit. فصل المصادر يفرض فصل
الاختصاص على مستوى البنية لا على مستوى النصيحة فقط.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from ..schemas import AgentId
from .base import ConnectorResult
from .macro import fetch_macro_series, fetch_worldbank
from .market import fetch_market_snapshot
from .news import fetch_news
from .social import fetch_social_pulse, fetch_x_pulse, fetch_youtube_pulse

Fetcher = Callable[[str], Awaitable[ConnectorResult]]


async def _news_geo(topic: str) -> ConnectorResult:
    return await fetch_news(topic, "geo")


async def _news_macro(topic: str) -> ConnectorResult:
    return await fetch_news(topic, "macro")


async def _news_breaking(topic: str) -> ConnectorResult:
    return await fetch_news(topic, "breaking")


async def _news_markets(topic: str) -> ConnectorResult:
    return await fetch_news(topic, "markets")


async def _market(_: str) -> ConnectorResult:
    return await fetch_market_snapshot()


async def _macro_series(_: str) -> ConnectorResult:
    return await fetch_macro_series()


async def _worldbank(_: str) -> ConnectorResult:
    return await fetch_worldbank()


CONNECTORS: dict[AgentId, list[Fetcher]] = {
    AgentId.SOCIAL: [fetch_social_pulse, fetch_x_pulse, fetch_youtube_pulse],
    AgentId.GEO: [_news_geo],
    AgentId.MACRO: [_news_macro, _macro_series, _worldbank],
    AgentId.BREAKING: [_news_breaking],
    AgentId.FLOW: [_market, _news_markets],
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
                getattr(fetcher, "__name__", "connector"), f"استثناء: {result}"
            ))
        else:
            out.append(result)
    return out
