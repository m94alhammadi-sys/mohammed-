"""المفكرة الاقتصادية — الأحداث المجدولة التي تحرّك الأسواق."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_TTL_SECONDS = 1800

_ENDPOINT = "https://economic-calendar.tradingview.com/events"

_IMPORTANCE_AR = {-1: "منخفض", 0: "متوسط", 1: "عالي"}

_COUNTRY_AR = {
    "US": "الولايات المتحدة", "EU": "منطقة اليورو", "GB": "بريطانيا", "JP": "اليابان",
    "CN": "الصين", "DE": "ألمانيا", "AE": "الإمارات", "SA": "السعودية", "CA": "كندا",
    "AU": "أستراليا", "CH": "سويسرا", "NZ": "نيوزلندا", "IN": "الهند", "TR": "تركيا",
}

DEFAULT_COUNTRIES = "US,EU,GB,JP,CN,DE,AE,SA"


def _fetch(from_dt: datetime, to_dt: datetime, countries: str) -> list[dict]:
    import httpx

    params = {
        "from": from_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "to": to_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "countries": countries,
    }
    headers = {
        "Origin": "https://www.tradingview.com",
        "Referer": "https://www.tradingview.com/",
        "User-Agent": "Mozilla/5.0 (compatible; EconomicAdvisorBot/1.0)",
    }
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        response = client.get(_ENDPOINT, params=params, headers=headers)
        response.raise_for_status()
        payload = response.json()

    return payload.get("result", []) if isinstance(payload, dict) else []


def _to_ar(event: dict) -> dict:
    country = event.get("country", "")
    return {
        "الحدث": event.get("title") or event.get("indicator") or "—",
        "الدولة": _COUNTRY_AR.get(country, country),
        "الأهمية": _IMPORTANCE_AR.get(event.get("importance"), "متوسط"),
        "التوقيت_UTC": event.get("date", ""),
        "الفعلي": event.get("actual"),
        "المتوقع": event.get("forecast"),
        "السابق": event.get("previous"),
        "الوحدة": event.get("unit") or "",
        "الفترة": event.get("period") or "",
    }


def upcoming_events(
    days_ahead: int = 7, countries: str = DEFAULT_COUNTRIES, only_high_impact: bool = False
) -> list[dict]:
    """أحداث اقتصادية قادمة خلال الأيام المقبلة."""
    key = f"upcoming:{days_ahead}:{countries}:{only_high_impact}"
    entry = _CACHE.get(key)
    if entry and time.time() - entry[0] < _TTL_SECONDS:
        return entry[1]

    now = datetime.now(timezone.utc)
    try:
        raw = _fetch(now, now + timedelta(days=days_ahead), countries)
    except Exception as exc:
        log.warning("تعذّر جلب المفكرة الاقتصادية: %s", exc)
        return [{"خطأ": f"تعذّر جلب المفكرة الاقتصادية: {exc}"}]

    events = [_to_ar(e) for e in raw]
    if only_high_impact:
        events = [e for e in events if e["الأهمية"] == "عالي"]
    events.sort(key=lambda e: e["التوقيت_UTC"])

    _CACHE[key] = (time.time(), events)
    return events


def today_events(countries: str = DEFAULT_COUNTRIES, only_high_impact: bool = True) -> list[dict]:
    """أحداث اليوم فقط."""
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        raw = _fetch(start, start + timedelta(days=1), countries)
    except Exception as exc:
        log.warning("تعذّر جلب أحداث اليوم: %s", exc)
        return [{"خطأ": f"تعذّر جلب أحداث اليوم: {exc}"}]

    events = [_to_ar(e) for e in raw]
    if only_high_impact:
        events = [e for e in events if e["الأهمية"] == "عالي"]
    events.sort(key=lambda e: e["التوقيت_UTC"])
    return events


def recent_releases(hours_back: int = 12, countries: str = DEFAULT_COUNTRIES) -> list[dict]:
    """بيانات صدرت للتو — يستخدمها الماسح لاكتشاف المفاجآت مقابل التوقعات."""
    now = datetime.now(timezone.utc)
    try:
        raw = _fetch(now - timedelta(hours=hours_back), now, countries)
    except Exception as exc:
        log.warning("تعذّر جلب البيانات الصادرة: %s", exc)
        return []

    out = []
    for event in raw:
        if event.get("actual") is None:
            continue
        item = _to_ar(event)
        actual, forecast = event.get("actual"), event.get("forecast")
        if isinstance(actual, (int, float)) and isinstance(forecast, (int, float)):
            item["المفاجأة"] = round(actual - forecast, 4)
            if forecast:
                item["المفاجأة_%"] = round((actual - forecast) / abs(forecast) * 100, 1)
        out.append(item)

    out.sort(key=lambda e: e["التوقيت_UTC"], reverse=True)
    return out
