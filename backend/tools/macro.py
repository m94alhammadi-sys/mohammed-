"""موصل بيانات الاقتصاد الكلي.

كان المحلل الاقتصادي أعمى تماماً بلا `FRED_API_KEY`. لم يعد كذلك:
بنك الاحتياطي الفيدرالي في سانت لويس ينشر كل سلسلة بصيغة CSV على
`fredgraph.csv` **بلا مفتاح**. المفتاح يبقى مفيداً (استجابة أسرع وحدود
أعلى وبيانات وصفية أغنى) لكنه لم يعد شرطاً للرؤية.
"""
from __future__ import annotations

import asyncio
import csv
import io
import json

from ..config import settings
from ..schemas import Evidence
from .base import ConnectorResult, FailureKind, clamp, fetch

# سلاسل FRED الأكثر تأثيراً على تسعير السيولة.
FRED_SERIES: dict[str, str] = {
    "CPIAUCSL": "مؤشر أسعار المستهلك الأمريكي",
    "FEDFUNDS": "سعر الفائدة الفيدرالي الفعلي",
    "UNRATE": "معدل البطالة الأمريكي",
    "DGS10": "عائد سندات الخزانة 10 سنوات",
    "T10Y2Y": "فارق العائد 10 سنوات ناقص سنتين",
    "WALCL": "إجمالي أصول الاحتياطي الفيدرالي",
}


def _series_evidence(series_id: str, label: str, latest_date: str,
                     latest: float, previous: float | None, source: str) -> Evidence:
    delta = f" | التغير عن القراءة السابقة {latest - previous:+.3f}" if previous is not None else ""
    return Evidence(
        source_type="official",
        title=f"{label} ({series_id}): {latest:g}{delta}",
        url=f"https://fred.stlouisfed.org/series/{series_id}",
        publisher=f"FRED — بنك الاحتياطي الفيدرالي في سانت لويس ({source})",
        published_at=latest_date,
        excerpt=f"الفترة المرجعية {latest_date} — بيانات قابلة للمراجعة لاحقاً",
        reliability=0.95,
    )


# ------------------------------------------------------- FRED بلا مفتاح

async def _fred_csv(series_id: str, label: str) -> Evidence | None:
    """مسار CSV العام — لا يحتاج مفتاحاً."""
    result = await fetch(
        "https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": series_id}
    )
    if not result.ok:
        return None

    rows = [r for r in csv.reader(io.StringIO(result.text)) if len(r) >= 2]
    if len(rows) < 2:
        return None

    # العمود الأول تاريخ والثاني قيمة؛ نمسح من الأحدث ونتجاهل الفراغات
    valid: list[tuple[str, float]] = []
    for date, raw, *_ in reversed(rows[1:]):
        if raw.strip() in ("", "."):
            continue
        try:
            valid.append((date.strip(), float(raw)))
        except ValueError:
            continue
        if len(valid) == 2:
            break

    if not valid:
        return None
    latest_date, latest = valid[0]
    previous = valid[1][1] if len(valid) > 1 else None
    return _series_evidence(series_id, label, latest_date, latest, previous, "CSV عام")


# ------------------------------------------------------- FRED بمفتاح

async def _fred_api(series_id: str, label: str) -> Evidence | None:
    result = await fetch(
        "https://api.stlouisfed.org/fred/series/observations",
        params={"series_id": series_id, "api_key": settings.fred_api_key or "",
                "file_type": "json", "sort_order": "desc", "limit": "2"},
    )
    if not result.ok:
        return None
    try:
        observations = json.loads(result.text).get("observations", [])
    except json.JSONDecodeError:
        return None
    if not observations:
        return None

    def _value(entry: dict) -> float | None:
        try:
            return float(entry["value"])
        except (KeyError, TypeError, ValueError):
            return None

    latest = _value(observations[0])
    if latest is None:
        return None
    previous = _value(observations[1]) if len(observations) > 1 else None
    return _series_evidence(
        series_id, label, observations[0].get("date", ""), latest, previous, "واجهة رسمية"
    )


async def _series(series_id: str, label: str) -> Evidence | None:
    """المفتاح أولاً إن وُجد، وإلا (أو عند فشله) المسار العام."""
    if settings.fred_api_key:
        evidence = await _fred_api(series_id, label)
        if evidence is not None:
            return evidence
    return await _fred_csv(series_id, label)


async def fetch_macro_series() -> ConnectorResult:
    results = await asyncio.gather(
        *(_series(sid, label) for sid, label in FRED_SERIES.items()),
        return_exceptions=True,
    )
    evidence = [r for r in results if isinstance(r, Evidence)]

    if not evidence:
        return ConnectorResult.failed(
            "macro:fred",
            f"لم تُجلب أي من {len(FRED_SERIES)} سلسلة عبر المسار العام"
            + ("" if settings.fred_api_key else " (ضبط FRED_API_KEY يحسّن الموثوقية)"),
            FailureKind.UNREACHABLE, attempted=len(FRED_SERIES),
        )

    keyed = "بمفتاح" if settings.fred_api_key else "بلا مفتاح"
    return ConnectorResult(
        name="macro:fred", ok=True,
        evidence=clamp(evidence, limit=len(evidence)),
        note=f"{len(evidence)}/{len(FRED_SERIES)} سلسلة ({keyed})",
        reached=len(evidence), attempted=len(FRED_SERIES),
    )


# ------------------------------------------------------------ البنك الدولي

async def fetch_worldbank(indicator: str = "FP.CPI.TOTL.ZG",
                          countries: str = "US;CN;SA;EU") -> ConnectorResult:
    """مؤشرات البنك الدولي — بلا مفتاح، لكنها سنوية ومتأخرة."""
    result = await fetch(
        f"https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}",
        params={"format": "json", "mrnev": "1"},
    )
    if not result.ok:
        return ConnectorResult.failed(
            "macro:worldbank", result.detail,
            result.kind or FailureKind.UNREACHABLE, attempted=1,
        )
    try:
        payload = json.loads(result.text)
        rows = payload[1] if len(payload) > 1 else []
    except (json.JSONDecodeError, IndexError, TypeError):
        return ConnectorResult.failed(
            "macro:worldbank", "استجابة غير متوقعة الشكل",
            FailureKind.MALFORMED, attempted=1,
        )

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
        for row in rows if isinstance(row, dict) and row.get("value") is not None
    ]
    if not evidence:
        return ConnectorResult.failed(
            "macro:worldbank", "لا قيم متاحة للمؤشر", FailureKind.EMPTY, attempted=1
        )
    return ConnectorResult(
        name="macro:worldbank", ok=True, evidence=clamp(evidence),
        note=f"{len(evidence)} دولة", reached=1, attempted=1,
    )
