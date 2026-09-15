"""أساس موصلات البيانات.

قاعدة الصدق: الموصل الذي يفشل يعيد `ok=False` وسبباً مقروءاً؛ ولا يعيد
أبداً بيانات مُصطنعة. الوكيل الذي يتلقى نتيجة فاشلة يرفع `degraded`
ويخفض ثقته، وهذا ما يظهر للمستخدم.

ما تضيفه هذه الطبقة فوق الصدق:
  * **تمييز نوع الفشل**: «مفتاح ناقص» ليس كـ«شبكة محجوبة» ليس كـ«لا نتائج».
    الأول إعداد ناقص يخص المستخدم، والثاني عطل مؤقت، والثالث نتيجة صحيحة.
  * **إعادة محاولة بتراجع أسّي** للأعطال العابرة وحدها (مهلة، 429، 5xx)،
    ولا إعادة لما لا فائدة من إعادته (404، 403).
  * **تخزين مؤقت بعمر محدد** حتى لا تُقصف المصادر في كل دورة.
  * **عميل HTTP مشترك** بتجميع اتصالات بدل عميل جديد لكل طلب.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

from ..config import settings
from ..schemas import Evidence

log = logging.getLogger(__name__)

# معرّف صادق فيه وسيلة تواصل — تشترطه بعض الجهات (SEC مثلاً) وتحجب دونه.
USER_AGENT = (
    "MajlisDecisionAgent/1.0 (multi-agent research client; "
    "+https://github.com/m94alhammadi-sys/mohammed-)"
)

MAX_ATTEMPTS = 3
BACKOFF_BASE_S = 0.6
CACHE_TTL_S = 180          # عمر الاستجابة المخزّنة مؤقتاً
_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class FailureKind(str, Enum):
    """لماذا فشل الموصل — يغيّر ما يُعرض للمستخدم وما يُطلب منه."""

    MISSING_KEY = "missing_key"   # إعداد ناقص: مفتاح غير مضبوط
    BLOCKED = "blocked"           # رفض الوصول: 403 أو وكيل حاجب
    UNREACHABLE = "unreachable"   # شبكة: مهلة أو انقطاع أو خطأ خادم
    EMPTY = "empty"               # وصلنا المصدر لكن لا نتائج مطابقة
    MALFORMED = "malformed"       # استجابة غير متوقعة الشكل

    @property
    def label(self) -> str:
        return {
            FailureKind.MISSING_KEY: "مفتاح غير مضبوط",
            FailureKind.BLOCKED: "وصول محجوب",
            FailureKind.UNREACHABLE: "تعذّر الوصول",
            FailureKind.EMPTY: "لا نتائج",
            FailureKind.MALFORMED: "استجابة غير صالحة",
        }[self]

    @property
    def is_config_gap(self) -> bool:
        """فشل يخص إعداد المستخدم لا عطلاً في النظام."""
        return self is FailureKind.MISSING_KEY

    @property
    def is_outage(self) -> bool:
        """عطل يمنع الرؤية فعلياً (يستوجب رفع `degraded`)."""
        return self in (FailureKind.BLOCKED, FailureKind.UNREACHABLE)


@dataclass
class ConnectorResult:
    name: str
    ok: bool
    evidence: list[Evidence] = field(default_factory=list)
    note: str = ""
    kind: FailureKind | None = None
    # المصادر الفرعية التي استجابت فعلاً مقابل التي جُرّبت
    reached: int = 0
    attempted: int = 0

    @classmethod
    def failed(
        cls, name: str, reason: str,
        kind: FailureKind = FailureKind.UNREACHABLE,
        attempted: int = 0,
    ) -> "ConnectorResult":
        return cls(name=name, ok=False, note=reason, kind=kind, attempted=attempted)

    @property
    def gap_text(self) -> str:
        """سطر الفجوة كما يظهر في `data_gaps` وفي التقرير."""
        prefix = self.kind.label if self.kind else "غير متاح"
        return f"{self.name} — {prefix}: {self.note}"


# ---------------------------------------------------------------- العميل

_clients: dict[int, httpx.AsyncClient] = {}


def _client() -> httpx.AsyncClient:
    """عميل مشترك لكل حلقة أحداث، بتجميع اتصالات وإعادة استخدامها."""
    loop_id = id(asyncio.get_running_loop())
    client = _clients.get(loop_id)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.http_timeout_s, connect=6.0),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=24, max_keepalive_connections=12),
            headers={"User-Agent": USER_AGENT, "Accept-Language": "ar,en;q=0.8"},
        )
        _clients[loop_id] = client
    return client


async def close_clients() -> None:
    """يُستدعى عند إغلاق التطبيق."""
    for client in list(_clients.values()):
        if not client.is_closed:
            await client.aclose()
    _clients.clear()


# ------------------------------------------------------------ التخزين المؤقت

_cache: dict[str, tuple[float, str]] = {}


def _cache_key(url: str, params: dict[str, str] | None) -> str:
    if not params:
        return url
    # ترتيب ثابت حتى لا يفلت التطابق بسبب ترتيب المفاتيح
    return url + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))


def clear_cache() -> None:
    _cache.clear()


# ---------------------------------------------------------------- الطلب

@dataclass
class Fetched:
    """استجابة ناجحة، أو فشل موصوف بنوعه."""

    text: str = ""
    ok: bool = False
    kind: FailureKind | None = None
    detail: str = ""
    status: int | None = None
    from_cache: bool = False

    def json(self) -> Any:
        import json

        return json.loads(self.text)


async def fetch(
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
    use_cache: bool = True,
    attempts: int = MAX_ATTEMPTS,
) -> Fetched:
    """طلب GET متسامح: يعيد `Fetched` موصوفاً بدل رفع استثناء.

    يعيد المحاولة على الأعطال العابرة وحدها، ويحترم `Retry-After` إن وُجد.
    """
    key = _cache_key(url, params)
    if use_cache:
        cached = _cache.get(key)
        if cached and time.monotonic() - cached[0] < CACHE_TTL_S:
            return Fetched(text=cached[1], ok=True, from_cache=True)

    last: Fetched = Fetched(kind=FailureKind.UNREACHABLE, detail="لم تُجرَ أي محاولة")

    for attempt in range(1, attempts + 1):
        try:
            response = await _client().get(
                url, params=params, headers=headers,
                timeout=timeout or settings.http_timeout_s,
            )
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
            last = Fetched(kind=FailureKind.UNREACHABLE, detail=_short(exc))
        except httpx.ProxyError as exc:
            # الوكيل الحاجب لا يُصلحه التكرار
            return Fetched(kind=FailureKind.BLOCKED, detail=_short(exc))
        except httpx.HTTPError as exc:
            last = Fetched(kind=FailureKind.UNREACHABLE, detail=_short(exc))
        else:
            if response.status_code < 400:
                if use_cache:
                    _cache[key] = (time.monotonic(), response.text)
                return Fetched(text=response.text, ok=True, status=response.status_code)

            if response.status_code in (401, 403):
                return Fetched(
                    kind=FailureKind.BLOCKED, status=response.status_code,
                    detail=f"رفض الوصول ({response.status_code})",
                )
            if response.status_code not in _RETRYABLE_STATUS:
                return Fetched(
                    kind=FailureKind.UNREACHABLE, status=response.status_code,
                    detail=f"حالة {response.status_code}",
                )
            last = Fetched(
                kind=FailureKind.UNREACHABLE, status=response.status_code,
                detail=f"حالة {response.status_code}",
            )
            await _honor_retry_after(response)

        if attempt < attempts:
            # تراجع أسّي مع تشويش عشوائي لتفادي تزامن المحاولات
            await asyncio.sleep(BACKOFF_BASE_S * (2 ** (attempt - 1)) + random.uniform(0, 0.3))

    log.info("تعذّر الوصول إلى %s بعد %d محاولة: %s", url, attempts, last.detail)
    return last


async def _honor_retry_after(response: httpx.Response) -> None:
    raw = response.headers.get("retry-after")
    if not raw:
        return
    try:
        delay = min(float(raw), 5.0)
    except ValueError:
        return
    await asyncio.sleep(delay)


def _short(exc: BaseException) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    return text[:160]


# ---------------------------------------------------------------- مساعدات

async def http_get(
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
) -> httpx.Response | None:
    """واجهة متوافقة مع الإصدار السابق: تعيد استجابة أو None.

    محفوظة لأن بعض الشيفرات والاختبارات تعتمدها؛ الجديد يستخدم `fetch`.
    """
    result = await fetch(url, params=params, headers=headers, timeout=timeout)
    if not result.ok:
        return None
    return httpx.Response(200, text=result.text)


def clamp(values: list[Evidence], limit: int | None = None) -> list[Evidence]:
    return values[: (limit or settings.max_evidence_per_tool)]


def dedupe(items: list[Evidence]) -> list[Evidence]:
    """يوحّد الأدلة داخل الموصل الواحد — المصدر المكرر عبر خلاصتين ليس دليلين."""
    seen: dict[str, Evidence] = {}
    for item in items:
        key = item.key()
        if key not in seen or item.reliability > seen[key].reliability:
            seen[key] = item
    return list(seen.values())
