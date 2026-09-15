"""اختبارات موصلات البيانات — بلا أي نداء شبكة حقيقي."""
import json

import pytest

from backend.schemas import AgentId
from backend.tools import registry
from backend.tools.base import (
    ConnectorResult, FailureKind, Fetched, clear_cache, dedupe,
)
from backend.tools.macro import fetch_macro_series, fetch_worldbank
from backend.tools.market import fetch_market_snapshot
from backend.tools.news import fetch_news, search_google_news
from backend.tools.social import fetch_social_pulse, fetch_x_pulse, fetch_youtube_pulse

pytestmark = pytest.mark.asyncio

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>الفيدرالي يرفع الفائدة</title><link>https://ex.com/1</link>
<pubDate>Mon, 15 Sep 2026</pubDate><description>قرار نقدي</description></item>
<item><title>خبر عن الذهب</title><link>https://ex.com/2</link>
<description>سوق المعادن</description></item>
</channel></rss>"""


@pytest.fixture(autouse=True)
def no_cache():
    """التخزين المؤقت مشترك بين الاختبارات — نُفرغه قبل كل واحد."""
    clear_cache()
    yield
    clear_cache()


def ok(text="", payload=None) -> Fetched:
    return Fetched(text=text if payload is None else json.dumps(payload), ok=True)


def dead(kind=FailureKind.UNREACHABLE, detail="محجوب") -> Fetched:
    return Fetched(ok=False, kind=kind, detail=detail)


def patch_fetch(monkeypatch, module, handler):
    """يستبدل `fetch` داخل وحدة موصل بعينها."""
    async def fake(url, **kwargs):
        return handler(url, kwargs)

    monkeypatch.setattr(f"backend.tools.{module}.fetch", fake)
    return fake


# ------------------------------------------------------------ طبقة الأساس

class TestBaseLayer:
    async def test_failure_kinds_classify_correctly(self):
        assert FailureKind.MISSING_KEY.is_config_gap is True
        assert FailureKind.BLOCKED.is_outage is True
        assert FailureKind.EMPTY.is_outage is False
        assert FailureKind.EMPTY.is_config_gap is False

    async def test_gap_text_names_the_kind(self):
        result = ConnectorResult.failed("social:x", "لا مفتاح", FailureKind.MISSING_KEY)
        assert "مفتاح غير مضبوط" in result.gap_text and "social:x" in result.gap_text

    async def test_dedupe_keeps_the_more_reliable_copy(self):
        from backend.schemas import Evidence

        items = [
            Evidence(title="أ", url="https://same", reliability=0.4),
            Evidence(title="أ", url="https://same", reliability=0.9),
        ]
        merged = dedupe(items)
        assert len(merged) == 1 and merged[0].reliability == 0.9


class TestRetryAndCache:
    async def test_transient_failure_is_retried(self, monkeypatch):
        from backend.tools import base

        attempts = {"n": 0}

        class FakeResponse:
            def __init__(self, status): self.status_code, self.text = status, "ok"
            headers: dict = {}

        class FakeClient:
            async def get(self, url, **kwargs):
                attempts["n"] += 1
                return FakeResponse(503 if attempts["n"] < 3 else 200)

        monkeypatch.setattr(base, "_client", lambda: FakeClient())
        monkeypatch.setattr(base, "BACKOFF_BASE_S", 0.001)
        result = await base.fetch("https://x/retry", use_cache=False)
        assert result.ok and attempts["n"] == 3

    async def test_forbidden_is_not_retried(self, monkeypatch):
        from backend.tools import base

        attempts = {"n": 0}

        class FakeResponse:
            status_code, text, headers = 403, "", {}

        class FakeClient:
            async def get(self, url, **kwargs):
                attempts["n"] += 1
                return FakeResponse()

        monkeypatch.setattr(base, "_client", lambda: FakeClient())
        result = await base.fetch("https://x/denied", use_cache=False)
        assert attempts["n"] == 1                       # لا فائدة من تكرار الرفض
        assert result.kind is FailureKind.BLOCKED

    async def test_cache_prevents_a_second_request(self, monkeypatch):
        from backend.tools import base

        calls = {"n": 0}

        class FakeResponse:
            status_code, text, headers = 200, "محتوى", {}

        class FakeClient:
            async def get(self, url, **kwargs):
                calls["n"] += 1
                return FakeResponse()

        monkeypatch.setattr(base, "_client", lambda: FakeClient())
        await base.fetch("https://x/cached")
        second = await base.fetch("https://x/cached")
        assert calls["n"] == 1 and second.from_cache is True

    async def test_cache_key_is_order_independent(self, monkeypatch):
        from backend.tools import base

        calls = {"n": 0}

        class FakeResponse:
            status_code, text, headers = 200, "محتوى", {}

        class FakeClient:
            async def get(self, url, **kwargs):
                calls["n"] += 1
                return FakeResponse()

        monkeypatch.setattr(base, "_client", lambda: FakeClient())
        await base.fetch("https://x/q", params={"a": "1", "b": "2"})
        await base.fetch("https://x/q", params={"b": "2", "a": "1"})
        assert calls["n"] == 1


# ---------------------------------------------------------------- الأخبار

class TestNews:
    async def test_parses_and_filters_by_topic(self, monkeypatch):
        patch_fetch(monkeypatch, "news", lambda url, kw: ok(RSS))
        result = await fetch_news("الذهب", "macro")
        assert result.ok
        assert any("الذهب" in e.title or "الذهب" in e.excerpt for e in result.evidence)

    async def test_backup_url_is_used_when_primary_dies(self, monkeypatch):
        seen = []

        async def fake(url, **kwargs):
            seen.append(url)
            # أول عنوان لكل خلاصة يسقط، والثاني ينجح
            return ok(RSS) if "press_all" in url or "aljazeera.com" in url else dead()

        monkeypatch.setattr("backend.tools.news.fetch", fake)
        result = await fetch_news("الفيدرالي", "macro")
        assert result.ok
        assert any("press_all" in u for u in seen)      # جُرّب البديل فعلاً

    async def test_search_fallback_fills_the_gap(self, monkeypatch):
        """خلاصات الأقسام تعطي ما هو رائج؛ البحث الموجّه يعطي ما طُلب."""
        def handler(url, kw):
            if "news.google.com" in url:
                return ok(RSS)
            return dead()

        patch_fetch(monkeypatch, "news", handler)
        result = await fetch_news("الذهب", "geo")
        assert result.ok and result.evidence

    async def test_total_outage_is_reported_not_faked(self, monkeypatch):
        patch_fetch(monkeypatch, "news", lambda url, kw: dead(FailureKind.BLOCKED))
        result = await fetch_news("الذهب", "geo")
        assert result.ok is False and result.evidence == []
        assert result.kind.is_outage

    async def test_malformed_xml_does_not_raise(self, monkeypatch):
        patch_fetch(monkeypatch, "news", lambda url, kw: ok("<not xml"))
        result = await fetch_news("الذهب", "geo")
        assert result.ok is False              # لا عناصر صالحة = لا ادعاء

    async def test_official_sources_rank_higher(self, monkeypatch):
        patch_fetch(monkeypatch, "news", lambda url, kw: ok(RSS))
        result = await fetch_news("الفيدرالي", "macro")
        assert max(e.reliability for e in result.evidence) >= 0.9

    async def test_search_picks_arabic_locale_for_arabic_topic(self, monkeypatch):
        seen = []

        async def fake(url, **kwargs):
            seen.append((url, kwargs))
            return ok(RSS)

        monkeypatch.setattr("backend.tools.news.fetch", fake)
        await search_google_news("الذهب والفائدة")
        assert "hl=ar" in seen[0][0]

    async def test_search_picks_english_locale_for_english_topic(self, monkeypatch):
        seen = []

        async def fake(url, **kwargs):
            seen.append(url)
            return ok(RSS)

        monkeypatch.setattr("backend.tools.news.fetch", fake)
        await search_google_news("gold rates")
        assert "hl=en" in seen[0]


# ----------------------------------------------------------------- السوق

class TestMarket:
    CSV = ("Symbol,Date,Time,Open,High,Low,Close,Volume\n"
           "XAUUSD,2026-09-15,20:00,2000,2050,1990,2040,100\n")
    YAHOO = {"chart": {"result": [{
        "meta": {"regularMarketPrice": 2040.0, "chartPreviousClose": 2000.0,
                 "currency": "USD", "regularMarketTime": 1789000000},
        "indicators": {"quote": [{"high": [2050.0], "low": [1990.0]}]},
    }]}}

    async def test_stooq_computes_session_change(self, monkeypatch):
        patch_fetch(monkeypatch, "market", lambda url, kw: ok(self.CSV))
        result = await fetch_market_snapshot([("الذهب", "xauusd", "GC=F")])
        assert result.ok and "+2.00%" in result.evidence[0].title
        assert result.evidence[0].publisher == "Stooq"

    async def test_yahoo_takes_over_when_stooq_dies(self, monkeypatch):
        def handler(url, kw):
            return dead() if "stooq" in url else ok(payload=self.YAHOO)

        patch_fetch(monkeypatch, "market", handler)
        result = await fetch_market_snapshot([("الذهب", "xauusd", "GC=F")])
        assert result.ok
        assert result.evidence[0].publisher == "Yahoo Finance"
        assert "+2.00%" in result.evidence[0].title

    async def test_both_providers_down_is_declared(self, monkeypatch):
        patch_fetch(monkeypatch, "market", lambda url, kw: dead(FailureKind.BLOCKED))
        result = await fetch_market_snapshot([("الذهب", "xauusd", "GC=F")])
        assert result.ok is False and "Stooq" in result.note and "Yahoo" in result.note

    async def test_no_data_marker_falls_through_to_yahoo(self, monkeypatch):
        blank = "Symbol,Date,Time,Open,High,Low,Close,Volume\nX,,,N/D,N/D,N/D,N/D,N/D\n"

        def handler(url, kw):
            return ok(blank) if "stooq" in url else ok(payload=self.YAHOO)

        patch_fetch(monkeypatch, "market", handler)
        result = await fetch_market_snapshot([("الذهب", "xauusd", "GC=F")])
        assert result.ok and result.evidence[0].publisher == "Yahoo Finance"


# ------------------------------------------------------------- الاقتصاد

class TestMacro:
    FRED_CSV = ("observation_date,CPIAUCSL\n"
                "2026-06-01,313.2\n2026-07-01,314.5\n2026-08-01,.\n")

    async def test_fred_works_without_a_key(self, monkeypatch):
        """أهم إصلاح: المحلل الاقتصادي لم يعد أعمى بلا مفتاح."""
        from backend.config import Settings

        monkeypatch.setattr("backend.tools.macro.settings", Settings(fred_api_key=None))
        patch_fetch(monkeypatch, "macro", lambda url, kw: ok(self.FRED_CSV))
        result = await fetch_macro_series()
        assert result.ok and result.evidence
        assert "بلا مفتاح" in result.note

    async def test_fred_csv_skips_empty_readings_and_computes_delta(self, monkeypatch):
        from backend.config import Settings

        monkeypatch.setattr("backend.tools.macro.settings", Settings(fred_api_key=None))
        patch_fetch(monkeypatch, "macro", lambda url, kw: ok(self.FRED_CSV))
        result = await fetch_macro_series()
        title = result.evidence[0].title
        assert "314.5" in title and "+1.3" in title       # تجاهل قراءة «.»

    async def test_api_path_is_preferred_when_key_present(self, monkeypatch):
        from backend.config import Settings

        seen = []

        async def fake(url, **kwargs):
            seen.append(url)
            if "api.stlouisfed.org" in url:
                return ok(payload={"observations": [
                    {"date": "2026-08-01", "value": "315.0"},
                    {"date": "2026-07-01", "value": "314.5"},
                ]})
            return dead()

        monkeypatch.setattr("backend.tools.macro.settings", Settings(fred_api_key="k"))
        monkeypatch.setattr("backend.tools.macro.fetch", fake)
        result = await fetch_macro_series()
        assert result.ok and "بمفتاح" in result.note
        assert any("api.stlouisfed.org" in u for u in seen)

    async def test_csv_rescues_a_failing_api_key(self, monkeypatch):
        from backend.config import Settings

        def handler(url, kw):
            return dead() if "api.stlouisfed.org" in url else ok(self.FRED_CSV)

        monkeypatch.setattr("backend.tools.macro.settings", Settings(fred_api_key="k"))
        patch_fetch(monkeypatch, "macro", handler)
        result = await fetch_macro_series()
        assert result.ok                                  # المفتاح فشل والعام أنقذ

    async def test_worldbank_flags_data_lag(self, monkeypatch):
        payload = [{"page": 1}, [{
            "country": {"value": "US"}, "indicator": {"value": "التضخم"},
            "value": 3.1, "date": "2024",
        }]]
        patch_fetch(monkeypatch, "macro", lambda url, kw: ok(payload=payload))
        result = await fetch_worldbank()
        assert result.ok and "متأخر" in result.evidence[0].excerpt

    async def test_worldbank_malformed_is_classified(self, monkeypatch):
        patch_fetch(monkeypatch, "macro", lambda url, kw: ok("ليس JSON"))
        result = await fetch_worldbank()
        assert result.kind is FailureKind.MALFORMED


# ------------------------------------------------------------- التواصل

class TestSocial:
    REDDIT = {"data": {"children": [{"data": {
        "title": "الذهب يقفز", "permalink": "/r/x/1", "score": 120,
        "num_comments": 30, "created_utc": 1_700_000_000, "selftext": "نص",
    }}]}}
    HN = {"hits": [{"title": "Gold rally", "url": "https://hn.test/1",
                    "points": 50, "num_comments": 10,
                    "created_at_i": 1_700_000_000, "objectID": "1"}]}

    async def test_reddit_extracts_engagement_velocity(self, monkeypatch):
        def handler(url, kw):
            return ok(payload=self.REDDIT) if "reddit" in url else dead()

        patch_fetch(monkeypatch, "social", handler)
        result = await fetch_social_pulse("الذهب")
        assert result.ok and "زخم" in result.evidence[0].excerpt

    async def test_hacker_news_rescues_a_blocked_reddit(self, monkeypatch):
        def handler(url, kw):
            return ok(payload=self.HN) if "algolia" in url else dead(FailureKind.BLOCKED)

        patch_fetch(monkeypatch, "social", handler)
        result = await fetch_social_pulse("gold")
        assert result.ok and "Hacker News" in result.note

    async def test_social_evidence_is_low_reliability_by_design(self, monkeypatch):
        def handler(url, kw):
            return ok(payload=self.REDDIT) if "reddit" in url else dead()

        patch_fetch(monkeypatch, "social", handler)
        result = await fetch_social_pulse("الذهب")
        assert all(e.reliability <= 0.4 for e in result.evidence)

    async def test_note_declares_sampling_bias(self, monkeypatch):
        def handler(url, kw):
            return ok(payload=self.REDDIT) if "reddit" in url else dead()

        patch_fetch(monkeypatch, "social", handler)
        result = await fetch_social_pulse("الذهب")
        assert "منحازة" in result.note

    async def test_full_outage_is_declared(self, monkeypatch):
        patch_fetch(monkeypatch, "social", lambda url, kw: dead(FailureKind.BLOCKED))
        result = await fetch_social_pulse("الذهب")
        assert result.ok is False and result.kind.is_outage

    async def test_x_without_token_is_a_config_gap_not_an_outage(self):
        result = await fetch_x_pulse("الذهب")
        assert result.kind is FailureKind.MISSING_KEY
        assert result.kind.is_config_gap and not result.kind.is_outage

    async def test_youtube_without_key_uses_limited_fallback(self, monkeypatch):
        patch_fetch(monkeypatch, "social", lambda url, kw: ok(RSS))
        result = await fetch_youtube_pulse("الذهب")
        assert result.ok and "محدود التغطية" in result.note


# ------------------------------------------------------------- السجل

class TestRegistry:
    async def test_source_access_is_partitioned_by_specialty(self):
        """فصل المصادر هو ما يفرض فصل الاختصاص بنيوياً."""
        social = {f.__name__ for f in registry.CONNECTORS[AgentId.SOCIAL]}
        macro = {f.__name__ for f in registry.CONNECTORS[AgentId.MACRO]}
        assert social & macro == set()
        assert any("social" in name for name in social)

    async def test_chief_has_no_direct_sources(self):
        assert AgentId.CHIEF not in registry.CONNECTORS

    async def test_gather_survives_a_throwing_connector(self, monkeypatch):
        async def boom(topic):
            raise RuntimeError("انفجار")

        monkeypatch.setitem(registry.CONNECTORS, AgentId.GEO, [boom])
        results = await registry.gather_context(AgentId.GEO, "الذهب")
        assert len(results) == 1 and results[0].ok is False
        assert "استثناء" in results[0].note

    async def test_coverage_separates_missing_keys_from_outages(self):
        results = [
            ConnectorResult("a", True, note="n"),
            ConnectorResult.failed("b", "لا مفتاح", FailureKind.MISSING_KEY),
            ConnectorResult.failed("c", "محجوب", FailureKind.BLOCKED),
        ]
        cover = registry.coverage(results)
        assert cover["missing_keys"] == ["b"] and cover["outages"] == ["c"]
        assert cover["blind"] is False            # مصدر واحد حي يكفي لرفع العمى

    async def test_coverage_flags_total_blindness(self):
        results = [ConnectorResult.failed("a", "محجوب", FailureKind.BLOCKED)]
        assert registry.coverage(results)["blind"] is True

    async def test_probe_reports_every_distinct_source(self, monkeypatch):
        async def fake_gather(topic):
            return ConnectorResult("probe", True, note="حي")

        for agent, fetchers in registry.CONNECTORS.items():
            monkeypatch.setitem(registry.CONNECTORS, agent, [fake_gather])

        probes = await registry.probe_sources()
        assert len(probes) == 1 and probes[0]["ok"] is True
        assert probes[0]["state"] == "يعمل"

    async def test_probe_marks_missing_keys_as_actionable(self, monkeypatch):
        async def needs_key(topic):
            return ConnectorResult.failed("s", "لا مفتاح", FailureKind.MISSING_KEY)

        for agent in list(registry.CONNECTORS):
            monkeypatch.setitem(registry.CONNECTORS, agent, [needs_key])

        probes = await registry.probe_sources()
        assert probes[0]["actionable"] is True
        assert probes[0]["state"] == "مفتاح غير مضبوط"
