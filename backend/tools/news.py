"""موصل الأخبار: قراءة خلاصات RSS الرسمية والإخبارية (بلا مفاتيح)."""
from __future__ import annotations

import asyncio
import re
from xml.etree import ElementTree as ET

from ..schemas import Evidence
from .base import ConnectorResult, clamp, http_get

# خلاصات عامة موثوقة نسبياً، مصنّفة حسب المجال.
FEEDS: dict[str, list[tuple[str, str, float]]] = {
    "geo": [
        ("Reuters World", "https://feeds.reuters.com/Reuters/worldNews", 0.85),
        ("UN News", "https://news.un.org/feed/subscribe/ar/news/all/rss.xml", 0.9),
        ("Al Jazeera", "https://www.aljazeera.net/aljazeerarss/a7c186be-1baa-4bd4-9d80-a84db769f779/73d0e1b4-532f-45ef-b135-bfdff8b8cab9", 0.7),
    ],
    "macro": [
        ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_monetary.xml", 0.95),
        ("ECB", "https://www.ecb.europa.eu/rss/press.html", 0.95),
        ("IMF", "https://www.imf.org/en/News/RSS?language=ENG", 0.9),
    ],
    "breaking": [
        ("Reuters Top", "https://feeds.reuters.com/reuters/topNews", 0.85),
        ("AP Top", "https://feeds.apnews.com/rss/apf-topnews", 0.85),
        ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", 0.8),
    ],
    "markets": [
        ("Reuters Business", "https://feeds.reuters.com/reuters/businessNews", 0.85),
        ("SEC Press", "https://www.sec.gov/news/pressreleases.rss", 0.95),
    ],
}

_TAG_RE = re.compile(r"<[^>]+>")


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
        link = _text(item, "link") or _attr_link(item)
        out.append(Evidence(
            source_type="news",
            title=title,
            url=link,
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


def _matches(evidence: Evidence, terms: list[str]) -> bool:
    if not terms:
        return True
    blob = f"{evidence.title} {evidence.excerpt}".lower()
    return any(term.lower() in blob for term in terms if len(term) > 2)


async def fetch_news(topic: str, category: str = "breaking") -> ConnectorResult:
    """يجلب عناوين الخلاصات ويصفّيها بكلمات الموضوع."""
    feeds = FEEDS.get(category, FEEDS["breaking"])
    responses = await asyncio.gather(
        *(http_get(url) for _, url, _ in feeds), return_exceptions=True
    )

    evidence: list[Evidence] = []
    reached = 0
    for (publisher, _, reliability), response in zip(feeds, responses):
        if not isinstance(response, object) or response is None or isinstance(response, BaseException):
            continue
        reached += 1
        evidence.extend(_parse_feed(response.text, publisher, reliability))

    if not reached:
        return ConnectorResult.failed(
            f"news:{category}", "تعذّر الوصول إلى أي خلاصة إخبارية (شبكة محجوبة أو منقطعة)"
        )

    terms = [t for t in re.split(r"[\s،,]+", topic) if t]
    filtered = [e for e in evidence if _matches(e, terms)] or evidence
    return ConnectorResult(
        name=f"news:{category}",
        ok=True,
        evidence=clamp(filtered),
        note=f"{reached}/{len(feeds)} خلاصة استجابت، {len(filtered)} عنصراً مطابقاً",
    )
