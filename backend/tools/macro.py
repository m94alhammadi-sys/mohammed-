"""موصل بيانات الاقتصاد الكلي: FRED (بمفتاح) والبنك الدولي (بلا مفتاح)."""
from __future__ import annotations

import asyncio

from ..config import settings
from ..schemas import Evidence
from .base import ConnectorResult, clamp, http_get

# سلاسل FRED الأكثر تأثيراً على تسعير السيولة.
FRED_SERIES: dict[str, str] = {
    "CPIAUCSL": "مؤشر أسعار المستهلك الأمريكي",
    "FEDFUNDS": "سعر الفائدة الفيدرالي الفعلي",
    "UNRATE": "معدل البطالة الأمريكي",
    "DGS10": "عائد سندات الخزانة 10 سنوات",
    "T10Y2Y": "فارق العائد 10 سنوات ناقص سنتين",
    "WALCL": "إجمالي أصول الاحتياطي الفيدرالي",
}


async def _fred_series(series_id: str, label: str) -> Evidence | None:
    response = await http_get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={"series_id": series_id, "api_key": settings.fred_api_key or "",
                "file_type": "json", "sort_order": "desc", "limit": "2"},
    )
    if response is None:
        return None
    observations = response.json().get("observations", [])
    if not observations:
        return None

    latest = observations[0]
    previous = observations[1] if len(observations) > 1 else None
    delta = ""
    try:
        if previous and previous["value"] not in (".", ""):
            delta = f" | التغير عن القراءة السابقة {float(latest['value']) - float(previous['value']):+.3f}"
    except (KeyError, ValueError):
        delta = ""

    return Evidence(
        source_type="official",
        title=f"{label} ({series_id}): {latest.get('value')}{delta}",
        url=f"https://fred.stlouisfed.org/series/{series_id}",
        publisher="FRED — بنك الاحتياطي الفيدرالي في سانت لويس",
        published_at=latest.get("date"),
        excerpt=f"الفترة المرجعية {latest.get('date')} — بيانات قابلة للمراجعة لاحقاً",
        reliability=0.95,
    )


async def fetch_macro_series() -> ConnectorResult:
    if not settings.fred_api_key:
        return ConnectorResult.failed(
            "macro:fred", "FRED_API_KEY غير مضبوط — لا سلاسل اقتصادية رسمية"
        )
    results = await asyncio.gather(
        *(_fred_series(sid, label) for sid, label in FRED_SERIES.items()),
        return_exceptions=True,
    )
    evidence = [r for r in results if isinstance(r, Evidence)]
    if not evidence:
        return ConnectorResult.failed("macro:fred", "لم تستجب واجهة FRED")
    return ConnectorResult(
        name="macro:fred", ok=True, evidence=clamp(evidence, limit=len(evidence)),
        note=f"{len(evidence)}/{len(FRED_SERIES)} سلسلة",
    )


async def fetch_worldbank(indicator: str = "FP.CPI.TOTL.ZG",
                          countries: str = "US;CN;SA;EU") -> ConnectorResult:
    """مؤشرات البنك الدولي — بلا مفتاح، لكنها سنوية ومتأخرة."""
    response = await http_get(
        f"https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}",
        params={"format": "json", "mrnev": "1"},
    )
    if response is None:
        return ConnectorResult.failed("macro:worldbank", "لم تستجب واجهة البنك الدولي")
    try:
        payload = response.json()
        rows = payload[1] if len(payload) > 1 else []
    except (ValueError, IndexError, TypeError):
        return ConnectorResult.failed("macro:worldbank", "استجابة غير متوقعة")

    evidence = [
        Evidence(
            source_type="official",
            title=(f"{row['country']['value']} — {row['indicator']['value']}: "
                   f"{row.get('value')} ({row.get('date')})"),
            url="https://data.worldbank.org/",
            publisher="البنك الدولي",
            published_at=str(row.get("date")),
            excerpt="بيان سنوي متأخر — لا يصلح لقراءة لحظية",
            reliability=0.85,
        )
        for row in rows if row.get("value") is not None
    ]
    if not evidence:
        return ConnectorResult.failed("macro:worldbank", "لا قيم متاحة للمؤشر")
    return ConnectorResult(name="macro:worldbank", ok=True, evidence=clamp(evidence))
