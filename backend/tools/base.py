"""أساس موصلات البيانات.

قاعدة الصدق: الموصل الذي يفشل يعيد `ok=False` وسبباً مقروءاً؛ ولا يعيد
أبداً بيانات مُصطنعة. الوكيل الذي يتلقى نتيجة فاشلة يرفع `degraded`
ويخفض ثقته، وهذا ما يظهر للمستخدم.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import httpx

from ..config import settings
from ..schemas import Evidence

log = logging.getLogger(__name__)

USER_AGENT = "MajlisDecisionAgent/1.0 (+multi-agent research client)"


@dataclass
class ConnectorResult:
    name: str
    ok: bool
    evidence: list[Evidence] = field(default_factory=list)
    note: str = ""

    @classmethod
    def failed(cls, name: str, reason: str) -> "ConnectorResult":
        return cls(name=name, ok=False, note=reason)


async def http_get(
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
) -> httpx.Response | None:
    """طلب GET متسامح مع الفشل: يعيد None بدل رفع استثناء."""
    merged = {"User-Agent": USER_AGENT, "Accept-Language": "ar,en;q=0.8"}
    merged.update(headers or {})
    try:
        async with httpx.AsyncClient(
            timeout=timeout or settings.http_timeout_s, follow_redirects=True
        ) as client:
            response = await client.get(url, params=params, headers=merged)
            response.raise_for_status()
            return response
    except (httpx.HTTPError, asyncio.TimeoutError) as exc:
        log.info("تعذّر الوصول إلى %s: %s", url, exc)
        return None


def clamp(values: list[Evidence], limit: int | None = None) -> list[Evidence]:
    return values[: (limit or settings.max_evidence_per_tool)]
