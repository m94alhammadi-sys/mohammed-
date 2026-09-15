"""اختبارات موصلات البيانات — بلا أي نداء شبكة حقيقي."""
import json
from types import SimpleNamespace

import pytest

from backend.schemas import AgentId
from backend.tools import registry
from backend.tools.macro import fetch_macro_series, fetch_worldbank
from backend.tools.market import fetch_insider_activity, fetch_market_snapshot
from backend.tools.news import fetch_news
from backend.tools.social import fetch_social_pulse, fetch_x_pulse

pytestmark = pytest.mark.asyncio

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>الفيدرالي يرفع الفائدة</title><link>https://ex.com/1</link>
<pubDate>Mon, 15 Sep 2026</pubDate><description>قرار نقدي</description></item>
<item><title>خبر عن الذهب</title><link>https://ex.com/2</link>
<description>سوق المعادن</description></item>
</channel></rss>"""


def response(text="", payload=None):
    return SimpleNamespace(
        text=text if payload is None else json.dumps(payload),
        json=lambda: payload,
    )


def patch_http(monkeypatch, module, handler):
    async def fake_get(url, **kwargs):
        return handler(url, kwargs)

    monkeypatch.setattr(f"backend.tools.{module}.http_get", fake_get)


class TestNews:
    async def test_parses_and_filters_by_topic(self, monkeypatch):
        patch_http(monkeypatch, "news", lambda url, kw: response(RSS))
        result = await fetch_news("الذهب", "macro")
        assert result.ok
        assert all("الذهب" in e.title or "الذهب" in e.excerpt for e in result.evidence)

    async def test_falls_back_to_all_items_when_nothing_matches(self, monkeypatch):
        patch_http(monkeypatch, "news", lambda url, kw: response(RSS))
        result = await fetch_news("موضوع لا يوجد", "macro")
        assert result.ok and len(result.evidence) > 0

    async def test_network_failure_is_reported_not_faked(self, monkeypatch):
        patch_http(monkeypatch, "news", lambda url, kw: None)
        result = await fetch_news("الذهب", "geo")
        assert result.ok is False and result.evidence == []
        assert "تعذّر" in result.note

    async def test_malformed_xml_does_not_raise(self, monkeypatch):
        patch_http(monkeypatch, "news", lambda url, kw: response("<not xml"))
        result = await fetch_news("الذهب", "geo")
        assert result.ok and result.evidence == []

    async def test_official_sources_rank_higher(self, monkeypatch):
        patch_http(monkeypatch, "news", lambda url, kw: response(RSS))
        result = await fetch_news("الفيدرالي", "macro")
        assert max(e.reliability for e in result.evidence) >= 0.9


class TestMarket:
    CSV = "Symbol,Date,Time,Open,High,Low,Close,Volume\nXAUUSD,2026-09-15,20:00,2000,2050,1990,2040,100\n"

    async def test_computes_session_change(self, monkeypatch):
        patch_http(monkeypatch, "market", lambda url, kw: response(self.CSV))
        result = await fetch_market_snapshot({"الذهب": "xauusd"})
        assert result.ok
        assert "+2.00%" in result.evidence[0].title

    async def test_no_data_marker_is_skipped(self, monkeypatch):
        blank = "Symbol,Date,Time,Open,High,Low,Close,Volume\nX,,,N/D,N/D,N/D,N/D,N/D\n"
        patch_http(monkeypatch, "market", lambda url, kw: response(blank))
        result = await fetch_market_snapshot({"س": "x"})
        assert result.ok is False

    async def test_insider_requires_a_key(self, monkeypatch):
        from backend.config import Settings

        monkeypatch.setattr("backend.tools.market.settings",
                            Settings(finnhub_api_key=None))
        result = await fetch_insider_activity("AAPL")
        assert result.ok is False and "FINNHUB" in result.note


class TestSocial:
    async def test_reddit_extracts_engagement_velocity(self, monkeypatch):
        payload = {"data": {"children": [{"data": {
            "title": "الذهب يقفز", "permalink": "/r/x/1", "score": 120,
            "num_comments": 30, "created_utc": 1_700_000_000, "selftext": "نص",
        }}]}}
        patch_http(monkeypatch, "social", lambda url, kw: response(payload=payload))
        result = await fetch_social_pulse("الذهب")
        assert result.ok
        assert "زخم" in result.evidence[0].excerpt

    async def test_social_evidence_is_low_reliability_by_design(self, monkeypatch):
        payload = {"data": {"children": [{"data": {
            "title": "ت", "permalink": "/r/x/1", "score": 1,
            "num_comments": 1, "created_utc": 1_700_000_000,
        }}]}}
        patch_http(monkeypatch, "social", lambda url, kw: response(payload=payload))
        result = await fetch_social_pulse("الذهب")
        assert all(e.reliability <= 0.4 for e in result.evidence)

    async def test_note_declares_sampling_bias(self, monkeypatch):
        payload = {"data": {"children": [{"data": {
            "title": "ت", "permalink": "/r/x/1", "score": 1,
            "num_comments": 1, "created_utc": 1_700_000_000,
        }}]}}
        patch_http(monkeypatch, "social", lambda url, kw: response(payload=payload))
        result = await fetch_social_pulse("الذهب")
        assert "منحازة" in result.note

    async def test_x_without_token_declares_blindness(self):
        result = await fetch_x_pulse("الذهب")
        assert result.ok is False and "X_BEARER_TOKEN" in result.note


class TestMacro:
    async def test_fred_without_key_is_declared(self):
        result = await fetch_macro_series()
        assert result.ok is False and "FRED_API_KEY" in result.note

    async def test_worldbank_flags_data_lag(self, monkeypatch):
        payload = [{"page": 1}, [{
            "country": {"value": "US"}, "indicator": {"value": "التضخم"},
            "value": 3.1, "date": "2024",
        }]]
        patch_http(monkeypatch, "macro", lambda url, kw: response(payload=payload))
        result = await fetch_worldbank()
        assert result.ok and "متأخر" in result.evidence[0].excerpt


class TestRegistry:
    @pytest.mark.asyncio(loop_scope="function")
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
