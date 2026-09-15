"""موصل منصات التواصل.

كان بوالعلوم يعتمد على مصدر واحد بلا مفتاح (Reddit JSON)، وهو أكثر ما
يُحجب من مراكز البيانات. الآن ثلاثة مسارات بلا مفاتيح:
Reddit JSON ← Reddit RSS (أكثر تسامحاً) ← Hacker News (واجهة Algolia
مفتوحة بالكامل). والمنصات المرخّصة (X، YouTube) تبقى خلف مفاتيحها.

تنبيه قانوني: لا تُستخدم هنا أي عملية كشط تخالف شروط خدمة المنصات؛
المستعمَل واجهات عامة وخلاصات منشورة للاستهلاك الآلي.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from urllib.parse import quote_plus

from ..config import settings
from ..schemas import Evidence
from .base import ConnectorResult, FailureKind, clamp, dedupe, fetch

SUBREDDITS = ["investing", "stocks", "economics", "worldnews", "wallstreetbets"]


def _age_hours(created_utc: float | None) -> float:
    if not created_utc:
        return 999.0
    return max((datetime.now(timezone.utc).timestamp() - created_utc) / 3600.0, 0.0)


def _engagement(title: str, url: str, publisher: str, score: int, comments: int,
                created_utc: float | None, body: str = "") -> Evidence:
    """يحوّل منشوراً إلى دليل، مع **معدل التفاعل في الساعة** لا الرقم المطلق.

    الرقم المطلق يكافئ المنشور القديم؛ ومقياس الزخم الصحيح هو السرعة.
    """
    hours = _age_hours(created_utc)
    velocity = (score + comments) / max(hours, 1.0)
    stamp = (datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat(timespec="minutes")
             if created_utc else None)
    return Evidence(
        source_type="social",
        title=title,
        url=url,
        publisher=publisher,
        published_at=stamp,
        excerpt=(f"تصويت {score} | تعليقات {comments} | عمر {hours:.1f} ساعة | "
                 f"زخم {velocity:.1f}/ساعة | {body[:200]}"),
        reliability=0.35,   # منشور مجهول الهوية: موثوقية منخفضة بنيوياً
    )


# ------------------------------------------------------------------ Reddit

async def _reddit_json(subreddit: str, query: str) -> list[Evidence]:
    result = await fetch(
        f"https://www.reddit.com/r/{subreddit}/search.json",
        params={"q": query, "restrict_sr": "1", "sort": "new",
                "limit": "10", "t": "week"},
    )
    if not result.ok:
        return []
    try:
        children = json.loads(result.text)["data"]["children"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []

    return [
        _engagement(
            f"r/{subreddit}: {post.get('title','')}",
            f"https://www.reddit.com{post.get('permalink','')}",
            "Reddit", post.get("score", 0), post.get("num_comments", 0),
            post.get("created_utc"), post.get("selftext") or "",
        )
        for post in (child.get("data", {}) for child in children)
    ]


async def _reddit_rss(subreddit: str, query: str) -> list[Evidence]:
    """مسار RSS — يُحجب أقل من مسار JSON، لكنه بلا مقاييس تفاعل."""
    result = await fetch(
        f"https://www.reddit.com/r/{subreddit}/search.rss",
        params={"q": query, "restrict_sr": "1", "sort": "new", "limit": "10"},
    )
    if not result.ok:
        return []

    from .news import _parse_feed

    items = _parse_feed(result.text, "Reddit (RSS)", 0.3)
    for item in items:
        item.source_type = "social"
        item.title = f"r/{subreddit}: {item.title}"
        item.excerpt = "بلا مقاييس تفاعل في مسار RSS — لا يصلح لقياس الزخم"
    return items


async def _hacker_news(query: str) -> list[Evidence]:
    """واجهة Algolia لـ Hacker News — مفتوحة بالكامل وبلا مفتاح."""
    result = await fetch(
        "https://hn.algolia.com/api/v1/search_by_date",
        params={"query": query, "tags": "story", "hitsPerPage": "15"},
    )
    if not result.ok:
        return []
    try:
        hits = json.loads(result.text).get("hits", [])
    except (json.JSONDecodeError, TypeError):
        return []

    out: list[Evidence] = []
    for hit in hits:
        created = hit.get("created_at_i")
        out.append(_engagement(
            f"HN: {hit.get('title') or hit.get('story_title') or ''}",
            hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
            "Hacker News", hit.get("points") or 0, hit.get("num_comments") or 0,
            float(created) if created else None,
        ))
    return out


async def fetch_social_pulse(topic: str) -> ConnectorResult:
    """نبض النقاش العام — Reddit بمسارين ثم Hacker News."""
    batches = await asyncio.gather(
        *(_reddit_json(sub, topic) for sub in SUBREDDITS), return_exceptions=True
    )
    evidence = [e for b in batches if isinstance(b, list) for e in b]
    sources = ["Reddit/JSON"] if evidence else []

    if not evidence:
        batches = await asyncio.gather(
            *(_reddit_rss(sub, topic) for sub in SUBREDDITS), return_exceptions=True
        )
        evidence = [e for b in batches if isinstance(b, list) for e in b]
        if evidence:
            sources.append("Reddit/RSS")

    hn = await _hacker_news(topic)
    if hn:
        evidence.extend(hn)
        sources.append("Hacker News")

    if not evidence:
        return ConnectorResult.failed(
            "social:public",
            "لم يستجب أي مصدر عام (Reddit بمسارَيه، و Hacker News)",
            FailureKind.UNREACHABLE, attempted=len(SUBREDDITS) * 2 + 1,
        )

    evidence = dedupe(evidence)
    evidence.sort(key=lambda e: e.published_at or "", reverse=True)
    return ConnectorResult(
        name="social:public", ok=True, evidence=clamp(evidence),
        note=(f"{len(evidence)} منشوراً عبر {'، '.join(sources)} — "
              "عينة منحازة لمنصات محدودة ولا تمثل الرأي العام"),
        reached=len(sources), attempted=3,
    )


# ------------------------------------------------------------ منصات مرخّصة

async def fetch_x_pulse(topic: str) -> ConnectorResult:
    """نبض X — يتطلب X_BEARER_TOKEN (الواجهة الرسمية)."""
    if not settings.x_bearer_token:
        return ConnectorResult.failed(
            "social:x", "X_BEARER_TOKEN غير مضبوط — لا قراءة من X",
            FailureKind.MISSING_KEY,
        )
    result = await fetch(
        "https://api.twitter.com/2/tweets/search/recent",
        params={"query": f"{topic} -is:retweet", "max_results": "25",
                "tweet.fields": "public_metrics,created_at,lang"},
        headers={"Authorization": f"Bearer {settings.x_bearer_token}"},
    )
    if not result.ok:
        return ConnectorResult.failed(
            "social:x", result.detail, result.kind or FailureKind.UNREACHABLE, attempted=1
        )

    try:
        items = json.loads(result.text).get("data", [])
    except (json.JSONDecodeError, TypeError):
        return ConnectorResult.failed(
            "social:x", "استجابة غير متوقعة", FailureKind.MALFORMED, attempted=1
        )

    evidence = []
    for item in items[: settings.max_evidence_per_tool]:
        metrics = item.get("public_metrics", {})
        created = item.get("created_at")
        stamp = None
        if created:
            try:
                stamp = datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp()
            except ValueError:
                stamp = None
        evidence.append(_engagement(
            (item.get("text") or "")[:160],
            f"https://x.com/i/status/{item.get('id')}", "X",
            metrics.get("like_count", 0),
            metrics.get("reply_count", 0) + metrics.get("retweet_count", 0), stamp,
        ))

    if not evidence:
        return ConnectorResult.failed(
            "social:x", "لا منشورات مطابقة", FailureKind.EMPTY, attempted=1
        )
    return ConnectorResult(name="social:x", ok=True, evidence=evidence,
                           note=f"{len(evidence)} منشوراً", reached=1, attempted=1)


async def fetch_youtube_pulse(topic: str) -> ConnectorResult:
    """اتجاهات YouTube — بمفتاح رسمي، أو خلاصة بحث عامة كبديل محدود."""
    if not settings.youtube_api_key:
        return await _youtube_rss(topic)

    result = await fetch(
        "https://www.googleapis.com/youtube/v3/search",
        params={"part": "snippet", "q": topic, "order": "date", "maxResults": "10",
                "type": "video", "key": settings.youtube_api_key},
    )
    if not result.ok:
        return await _youtube_rss(topic)

    try:
        items = json.loads(result.text).get("items", [])
    except (json.JSONDecodeError, TypeError):
        return ConnectorResult.failed(
            "social:youtube", "استجابة غير متوقعة", FailureKind.MALFORMED, attempted=1
        )

    evidence = [
        Evidence(
            source_type="social",
            title=item["snippet"]["title"],
            url=f"https://www.youtube.com/watch?v={item['id']['videoId']}",
            publisher=item["snippet"].get("channelTitle", "YouTube"),
            published_at=item["snippet"].get("publishedAt"),
            excerpt=item["snippet"].get("description", "")[:200],
            reliability=0.4,
        )
        for item in items if item.get("id", {}).get("videoId")
    ]
    if not evidence:
        return ConnectorResult.failed(
            "social:youtube", "لا فيديوهات مطابقة", FailureKind.EMPTY, attempted=1
        )
    return ConnectorResult(name="social:youtube", ok=True, evidence=clamp(evidence),
                           note=f"{len(evidence)} فيديو", reached=1, attempted=1)


async def _youtube_rss(topic: str) -> ConnectorResult:
    """بديل بلا مفتاح: نتائج فيديو عبر فهرس Google News.

    تغطية أضيق بكثير من الواجهة الرسمية، وتُعلَن كذلك صراحةً.
    """
    result = await fetch(
        "https://news.google.com/rss/search",
        params={"q": f"{topic} site:youtube.com", "hl": "ar", "gl": "SA", "ceid": "SA:ar"},
    )
    if not result.ok:
        return ConnectorResult.failed(
            "social:youtube",
            f"YOUTUBE_API_KEY غير مضبوط، وفشل البديل العام: {result.detail}",
            FailureKind.MISSING_KEY if not settings.youtube_api_key
            else (result.kind or FailureKind.UNREACHABLE),
            attempted=1,
        )

    from .news import _parse_feed

    evidence = _parse_feed(result.text, "YouTube (عبر فهرس عام)", 0.3)
    for item in evidence:
        item.source_type = "social"
    if not evidence:
        return ConnectorResult.failed(
            "social:youtube", "لا نتائج في البديل العام", FailureKind.EMPTY, attempted=1
        )
    return ConnectorResult(
        name="social:youtube", ok=True, evidence=clamp(evidence),
        note=(f"{len(evidence)} نتيجة عبر بديل عام محدود التغطية — "
              "اضبط YOUTUBE_API_KEY لتغطية حقيقية"),
        reached=1, attempted=1,
    )


# التسمية القديمة محفوظة للتوافق
fetch_reddit_pulse = fetch_social_pulse
