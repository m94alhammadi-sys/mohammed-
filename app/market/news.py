"""جلب الأخبار المالية من مصادر RSS عربية وعالمية + تقدير حساسية الخبر."""

from __future__ import annotations

import html
import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote_plus

from .symbols import CATALOG, to_ticker

log = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_TTL_SECONDS = 600

# مصادر عامة ثابتة
FEEDS = {
    "cnbc_markets": "https://www.cnbc.com/id/20910258/device/rss/rss.html",
    "cnbc_economy": "https://www.cnbc.com/id/20910258/device/rss/rss.html",
    "investing_ar": "https://sa.investing.com/rss/news_25.rss",
    "argaam": "https://www.argaam.com/ar/rss/latest",
    "emaratalyoum_business": "https://www.emaratalyoum.com/business/rss",
    "albayan_economy": "https://www.albayan.ae/economy/rss",
}

# كلمات تدل على أحداث تحرّك السوق بقوة (عربي + إنجليزي)
_HIGH_IMPACT = [
    "فائدة", "الفيدرالي", "تضخم", "ركود", "عقوبات", "حرب", "أوبك", "خفض الإنتاج",
    "أرباح", "إفلاس", "اندماج", "استحواذ", "طرح عام", "تصنيف ائتماني", "تخفيض التصنيف",
    "fed", "rate cut", "rate hike", "inflation", "cpi", "recession", "sanctions",
    "opec", "earnings", "bankruptcy", "merger", "acquisition", "ipo", "downgrade",
    "default", "tariff", "stimulus", "crash", "surge", "plunge",
]

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str | None, limit: int = 300) -> str:
    if not text:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", text))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def _impact(title: str, summary: str) -> str:
    blob = f"{title} {summary}".lower()
    hits = sum(1 for word in _HIGH_IMPACT if word in blob)
    if hits >= 3:
        return "عالي"
    if hits >= 1:
        return "متوسط"
    return "عادي"


def _parse_feed(url: str, limit: int) -> list[dict]:
    import feedparser

    parsed = feedparser.parse(url)
    if getattr(parsed, "bozo", 0) and not parsed.entries:
        raise RuntimeError(getattr(parsed, "bozo_exception", "تعذّر قراءة التغذية"))

    items: list[dict] = []
    for entry in parsed.entries[:limit]:
        published = ""
        if getattr(entry, "published_parsed", None):
            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).isoformat()
        title = _clean(getattr(entry, "title", ""), 200)
        summary = _clean(getattr(entry, "summary", ""), 300)
        items.append({
            "العنوان": title,
            "الملخص": summary,
            "الرابط": getattr(entry, "link", ""),
            "المصدر": _clean(getattr(getattr(entry, "source", None), "title", "") or parsed.feed.get("title", ""), 60),
            "التاريخ": published,
            "الأهمية": _impact(title, summary),
        })
    return items


def _cached(key: str, builder, ttl: int = _TTL_SECONDS) -> list[dict]:
    entry = _CACHE.get(key)
    if entry and time.time() - entry[0] < ttl:
        return entry[1]
    value = builder()
    _CACHE[key] = (time.time(), value)
    return value


def search_news(query: str, limit: int = 10, lang: str = "ar") -> list[dict]:
    """بحث إخباري حر عبر Google News RSS — يدعم العربية والإنجليزية."""
    region = "AE" if lang == "ar" else "US"
    url = (
        f"https://news.google.com/rss/search?q={quote_plus(query)}"
        f"&hl={lang}&gl={region}&ceid={region}:{lang}"
    )

    def build() -> list[dict]:
        try:
            return _parse_feed(url, limit)
        except Exception as exc:
            log.warning("فشل البحث الإخباري عن '%s': %s", query, exc)
            return []

    return _cached(f"search:{lang}:{query}:{limit}", build)


def ticker_news(symbol: str, limit: int = 8) -> list[dict]:
    """أخبار خاصة برمز معيّن."""
    ticker = to_ticker(symbol)
    info = CATALOG.get(ticker)

    def build() -> list[dict]:
        items: list[dict] = []
        # 1) تغذية ياهو الخاصة بالرمز (تعمل مع الأسهم الأمريكية أساساً)
        yahoo = (
            f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={quote_plus(ticker)}"
            "&region=US&lang=en-US"
        )
        try:
            items.extend(_parse_feed(yahoo, limit))
        except Exception as exc:
            log.debug("تغذية ياهو غير متاحة لـ %s: %s", ticker, exc)

        # 2) بحث بالاسم العربي/الإنجليزي — يغطي الأسهم الإماراتية
        if len(items) < limit and info:
            items.extend(search_news(f"{info.ar} OR {info.en}", limit - len(items)))
        elif len(items) < limit:
            items.extend(search_news(ticker, limit - len(items)))

        seen: set[str] = set()
        unique = []
        for item in items:
            if item["العنوان"] and item["العنوان"] not in seen:
                seen.add(item["العنوان"])
                unique.append(item)
        return unique[:limit]

    return _cached(f"ticker:{ticker}:{limit}", build)


def market_headlines(region: str = "global", limit: int = 12) -> list[dict]:
    """أهم عناوين السوق. ``region``: global | uae | gulf."""
    queries = {
        "global": ["global markets stocks", "federal reserve interest rates", "oil prices"],
        "uae": ["سوق دبي المالي", "سوق أبوظبي للأوراق المالية", "اقتصاد الإمارات"],
        "gulf": ["أسواق الخليج المالية", "أوبك النفط", "الاقتصاد السعودي"],
    }
    lang = "en" if region == "global" else "ar"

    def build() -> list[dict]:
        items: list[dict] = []
        per_query = max(limit // len(queries.get(region, queries["global"])), 3)
        for query in queries.get(region, queries["global"]):
            items.extend(search_news(query, per_query, lang=lang))

        seen: set[str] = set()
        unique = []
        for item in items:
            if item["العنوان"] and item["العنوان"] not in seen:
                seen.add(item["العنوان"])
                unique.append(item)
        unique.sort(key=lambda i: (i["الأهمية"] != "عالي", i["التاريخ"]), reverse=False)
        return unique[:limit]

    return _cached(f"headlines:{region}:{limit}", build)


def breaking_risk_scan(limit: int = 15) -> list[dict]:
    """يرصد العناوين عالية التأثير فقط — يستخدمه الماسح لاكتشاف الصدمات."""
    pool = market_headlines("global", limit) + market_headlines("uae", limit // 2)
    return [item for item in pool if item["الأهمية"] == "عالي"][:limit]
