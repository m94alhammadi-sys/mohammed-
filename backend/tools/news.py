"""موصل الأخبار: خلاصات RSS رسمية وإخبارية، بلا مفاتيح.

مبدآن يعالجان الفشل بدل إخفائه:
  1. **بدائل لكل مصدر**: لكل خلاصة عنوان أساسي وعناوين احتياطية. سقوط
     مزوّد واحد لم يعد يُعمي الوكيل.
  2. **بحث موجّه بالموضوع**: خلاصات الأقسام تعطي ما هو رائج لا ما طُلب.
     خلاصة بحث Google News تقبل استعلاماً عربياً وتعيد نتائج مطابقة
     فعلاً، فهي الملاذ الذي يملأ الفراغ حين لا تذكر الخلاصات الموضوع.
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET

from ..schemas import Evidence
from .base import ConnectorResult, FailureKind, clamp, dedupe, fetch

# (الناشر، [عناوين بالترتيب: الأساسي ثم البدائل]، الموثوقية)
Feed = tuple[str, list[str], float]

FEEDS: dict[str, list[Feed]] = {
    "geo": [
        ("Reuters (عبر Google News)", [
            "https://news.google.com/rss/search?q=when:2d+site:reuters.com+world&hl=en&gl=US&ceid=US:en",
        ], 0.85),
        ("UN News", [
            "https://news.un.org/ar/feed/subscribe/ar/news/all/rss.xml",
            "https://news.un.org/en/feed/subscribe/en/news/all/rss.xml",
        ], 0.9),
        ("Al Jazeera", [
            "https://www.aljazeera.net/aljazeerarss/a7c186be-1baa-4bd4-9d80-a84db769f779/73d0e1b4-532f-45ef-b135-bfdff8b8cab9",
            "https://www.aljazeera.com/xml/rss/all.xml",
        ], 0.7),
        ("BBC World", [
            "https://feeds.bbci.co.uk/news/world/rss.xml",
        ], 0.8),
    ],
    "macro": [
        ("Federal Reserve", [
            "https://www.federalreserve.gov/feeds/press_monetary.xml",
            "https://www.federalreserve.gov/feeds/press_all.xml",
        ], 0.95),
        ("ECB", [
            "https://www.ecb.europa.eu/rss/press.html",
        ], 0.95),
        ("IMF", [
            "https://www.imf.org/en/News/RSS?language=ENG",
        ], 0.9),
        ("CNBC Economy", [
            "https://www.cnbc.com/id/20910258/device/rss/rss.html",
        ], 0.75),
    ],
    "breaking": [
        ("BBC World", [
            "https://feeds.bbci.co.uk/news/world/rss.xml",
        ], 0.8),
        ("AP (عبر Google News)", [
            "https://news.google.com/rss/search?q=when:1d+site:apnews.com&hl=en&gl=US&ceid=US:en",
        ], 0.85),
        ("Al Jazeera", [
            "https://www.aljazeera.com/xml/rss/all.xml",
            "https://www.aljazeera.net/aljazeerarss/a7c186be-1baa-4bd4-9d80-a84db769f779/73d0e1b4-532f-45ef-b135-bfdff8b8cab9",
        ], 0.7),
    ],
    "markets": [
        ("SEC Press", [
            "https://www.sec.gov/news/pressreleases.rss",
        ], 0.95),
        ("CNBC Markets", [
            "https://www.cnbc.com/id/20910258/device/rss/rss.html",
            "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        ], 0.75),
        ("Yahoo Finance", [
            "https://finance.yahoo.com/news/rssindex",
        ], 0.7),
        ("MarketWatch", [
            "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        ], 0.75),
    ],
}

# لغة البحث الاحتياطي حسب المجال
_GOOGLE_NEWS_LOCALES = {
    "ar": ("ar", "SA", "SA:ar"),
    "en": ("en", "US", "US:en"),
}

_TAG_RE = re.compile(r"<[^>]+>")
_ARABIC_RE = re.compile(r"[؀-ۿ]")


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return _TAG_RE.sub(" ", text).replace("&nbsp;", " ").strip()


def _parse_feed(xml_text: str, publisher: str, reliability: float) -> list[Evidence]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    items = root.findall(".//item") or root.findall(
        ".//{http://www.w3.org/2005/Atom}entry"
    )
    out: list[Evidence] = []
    for item in items:
        title = _clean(_text(item, "title"))
        if not title:
            continue
        out.append(Evidence(
            source_type="news",
            title=title,
            url=_text(item, "link") or _attr_link(item),
            publisher=publisher,
            published_at=_text(item, "pubDate") or _text(item, "updated"),
            excerpt=_clean(_text(item, "description") or _text(item, "summary"))[:400],
            reliability=reliability,
        ))
    return out


def _text(node: ET.Element, tag: str) -> str | None:
    for candidate in (tag, f"{{http://www.w3.org/2005/Atom}}{tag}"):
        found = node.find(candidate)
        if found is not None and found.text:
            return found.text.strip()
    return None


def _attr_link(node: ET.Element) -> str | None:
    link = node.find("{http://www.w3.org/2005/Atom}link")
    return link.get("href") if link is not None else None


def _terms(topic: str) -> list[str]:
    return [t for t in re.split(r"[\s،,]+", topic) if len(t) > 2]


def _matches(evidence: Evidence, terms: list[str]) -> bool:
    if not terms:
        return True
    blob = f"{evidence.title} {evidence.excerpt}".lower()
    return any(term.lower() in blob for term in terms)


async def _load_feed(feed: Feed) -> list[Evidence]:
    """يجرّب عناوين الخلاصة بالترتيب — أول عنوان يردّ بعناصر صالحة يفوز.

    وجود بديل هو الفرق بين «مزوّد سقط فسقط الوكيل» و«مزوّد سقط فانتقلنا».
    """
    publisher, urls, reliability = feed
    for url in urls:
        result = await fetch(url)
        if not result.ok:
            continue
        items = _parse_feed(result.text, publisher, reliability)
        if items:
            return items
    return []


async def search_google_news(topic: str, *, lang: str | None = None) -> ConnectorResult:
    """بحث موجّه بالموضوع عبر خلاصة Google News — بلا مفتاح ويقبل العربية.

    هذه ليست مصدراً بذاتها بل فهرس لمصادر أخرى، لذلك موثوقيتها متوسطة
    ويجب أن يقرأ الوكيل الناشر الأصلي من عنوان الخبر.
    """
    if not topic.strip():
        return ConnectorResult.failed(
            "news:search", "لا موضوع للبحث عنه", FailureKind.EMPTY
        )

    detected = lang or ("ar" if _ARABIC_RE.search(topic) else "en")
    hl, gl, ceid = _GOOGLE_NEWS_LOCALES.get(detected, _GOOGLE_NEWS_LOCALES["en"])
    url = (
        f"https://news.google.com/rss/search?q={quote_plus(topic)}+when:7d"
        f"&hl={hl}&gl={gl}&ceid={ceid}"
    )

    result = await fetch(url)
    if not result.ok:
        return ConnectorResult.failed(
            "news:search", result.detail, result.kind or FailureKind.UNREACHABLE,
            attempted=1,
        )

    evidence = _parse_feed(result.text, "Google News (فهرس مصادر)", 0.6)
    if not evidence:
        return ConnectorResult.failed(
            "news:search", f"لا نتائج لـ «{topic}»", FailureKind.EMPTY, attempted=1
        )
    return ConnectorResult(
        name="news:search", ok=True, evidence=clamp(evidence),
        note=f"{len(evidence)} نتيجة مطابقة للموضوع ({detected})",
        reached=1, attempted=1,
    )


async def fetch_news(topic: str, category: str = "breaking") -> ConnectorResult:
    """يجلب خلاصات المجال ويصفّيها بالموضوع، ويُكمل النقص ببحث موجّه."""
    feeds = FEEDS.get(category, FEEDS["breaking"])
    batches = await asyncio.gather(
        *(_load_feed(feed) for feed in feeds), return_exceptions=True
    )

    evidence: list[Evidence] = []
    reached = 0
    for batch in batches:
        if isinstance(batch, list) and batch:
            reached += 1
            evidence.extend(batch)

    terms = _terms(topic)
    matched = [e for e in evidence if _matches(e, terms)]

    # الخلاصات تعطي ما هو رائج لا ما طُلب؛ نُكمل ببحث موجّه عند قلة التطابق
    search_note = ""
    if len(matched) < 3:
        search = await search_google_news(topic)
        if search.ok:
            matched.extend(search.evidence)
            reached += 1
            search_note = " + بحث موجّه"
        elif not evidence:
            return ConnectorResult.failed(
                f"news:{category}",
                f"لم تستجب أي خلاصة من {len(feeds)}، وفشل البحث الموجّه: {search.note}",
                search.kind or FailureKind.UNREACHABLE,
                attempted=len(feeds) + 1,
            )

    if not evidence and not matched:
        return ConnectorResult.failed(
            f"news:{category}", f"لم تستجب أي خلاصة من {len(feeds)}",
            FailureKind.UNREACHABLE, attempted=len(feeds),
        )

    # لا مطابق للموضوع لكن الخلاصات حية: نعيد الخلفية العامة موسومة
    fallback = not matched
    final = dedupe(matched or evidence)
    return ConnectorResult(
        name=f"news:{category}", ok=True, evidence=clamp(final),
        note=(f"{reached}/{len(feeds)} خلاصة استجابت{search_note}، "
              + (f"{len(final)} عنصراً مطابقاً" if not fallback
                 else "لا عنصر مطابق للموضوع — أُعيدت خلفية المجال العامة")),
        reached=reached, attempted=len(feeds),
    )
