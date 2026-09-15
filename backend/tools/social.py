"""موصل منصات التواصل.

Reddit متاح بلا مفتاح عبر واجهة JSON العامة. المنصات الأخرى (X، YouTube)
تتطلب مفاتيح رسمية؛ في غيابها يُعلن الموصل عجزه صراحة بدل تلفيق أرقام.
تنبيه قانوني: لا تُستخدم هنا أي عملية كشط تخالف شروط خدمة المنصات.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from ..config import settings
from ..schemas import Evidence
from .base import ConnectorResult, clamp, http_get

# منتديات مالية عامة ذات حجم نقاش مرتفع.
SUBREDDITS = ["investing", "stocks", "economics", "worldnews", "wallstreetbets"]


def _age_hours(created_utc: float | None) -> float:
    if not created_utc:
        return 999.0
    delta = datetime.now(timezone.utc).timestamp() - created_utc
    return max(delta / 3600.0, 0.0)


async def _reddit_search(subreddit: str, query: str) -> list[Evidence]:
    response = await http_get(
        f"https://www.reddit.com/r/{subreddit}/search.json",
        params={"q": query, "restrict_sr": "1", "sort": "new", "limit": "10", "t": "week"},
    )
    if response is None:
        return []
    try:
        children = response.json()["data"]["children"]
    except (KeyError, ValueError):
        return []

    out: list[Evidence] = []
    for child in children:
        post = child.get("data", {})
        score = post.get("score", 0)
        comments = post.get("num_comments", 0)
        hours = _age_hours(post.get("created_utc"))
        # معدل التفاعل في الساعة مؤشر زخم أفضل من الرقم المطلق
        velocity = (score + comments) / max(hours, 1.0)
        out.append(Evidence(
            source_type="social",
            title=f"r/{subreddit}: {post.get('title','')}",
            url=f"https://www.reddit.com{post.get('permalink','')}",
            publisher="Reddit",
            published_at=datetime.fromtimestamp(
                post.get("created_utc", 0), tz=timezone.utc
            ).isoformat(timespec="minutes"),
            excerpt=(f"تصويت {score} | تعليقات {comments} | عمر {hours:.1f} ساعة | "
                     f"زخم {velocity:.1f}/ساعة | {(post.get('selftext') or '')[:200]}"),
            reliability=0.35,   # منشور مجهول الهوية: موثوقية منخفضة بنيوياً
        ))
    return out


async def fetch_social_pulse(topic: str) -> ConnectorResult:
    """نبض النقاش العام حول الموضوع عبر منتديات Reddit."""
    batches = await asyncio.gather(
        *(_reddit_search(sub, topic) for sub in SUBREDDITS), return_exceptions=True
    )
    evidence = [e for batch in batches if isinstance(batch, list) for e in batch]
    if not evidence:
        return ConnectorResult.failed(
            "social:reddit", "تعذّر الوصول إلى Reddit أو لا نتائج للموضوع"
        )
    evidence.sort(key=lambda e: e.published_at or "", reverse=True)
    return ConnectorResult(
        name="social:reddit", ok=True, evidence=clamp(evidence),
        note=(f"عينة من {len(SUBREDDITS)} مجتمعات، {len(evidence)} منشوراً — "
              "عينة منحازة لمنصة واحدة ولا تمثل الرأي العام"),
    )


async def fetch_x_pulse(topic: str) -> ConnectorResult:
    """نبض X — يتطلب X_BEARER_TOKEN (واجهة X الرسمية)."""
    if not settings.x_bearer_token:
        return ConnectorResult.failed(
            "social:x", "X_BEARER_TOKEN غير مضبوط — لا قراءة من X"
        )
    response = await http_get(
        "https://api.twitter.com/2/tweets/search/recent",
        params={"query": f"{topic} -is:retweet lang:ar OR lang:en",
                "max_results": "25",
                "tweet.fields": "public_metrics,created_at,lang"},
        headers={"Authorization": f"Bearer {settings.x_bearer_token}"},
    )
    if response is None:
        return ConnectorResult.failed("social:x", "لم تستجب واجهة X")

    items = response.json().get("data", [])
    evidence = [
        Evidence(
            source_type="social",
            title=(item.get("text") or "")[:160],
            url=f"https://x.com/i/status/{item.get('id')}",
            publisher="X",
            published_at=item.get("created_at"),
            excerpt=str(item.get("public_metrics", {})),
            reliability=0.35,
        )
        for item in items[: settings.max_evidence_per_tool]
    ]
    if not evidence:
        return ConnectorResult.failed("social:x", "لا منشورات مطابقة")
    return ConnectorResult(name="social:x", ok=True, evidence=evidence)


async def fetch_youtube_pulse(topic: str) -> ConnectorResult:
    """اتجاهات YouTube — يتطلب YOUTUBE_API_KEY."""
    if not settings.youtube_api_key:
        return ConnectorResult.failed(
            "social:youtube", "YOUTUBE_API_KEY غير مضبوط — لا قراءة من YouTube"
        )
    response = await http_get(
        "https://www.googleapis.com/youtube/v3/search",
        params={"part": "snippet", "q": topic, "order": "date", "maxResults": "10",
                "type": "video", "key": settings.youtube_api_key},
    )
    if response is None:
        return ConnectorResult.failed("social:youtube", "لم تستجب واجهة YouTube")

    items = response.json().get("items", [])
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
        for item in items[: settings.max_evidence_per_tool]
        if item.get("id", {}).get("videoId")
    ]
    if not evidence:
        return ConnectorResult.failed("social:youtube", "لا فيديوهات مطابقة")
    return ConnectorResult(name="social:youtube", ok=True, evidence=evidence)
