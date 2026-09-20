import pytest

from advisor import market_data
from advisor.market_data import MarketSnapshot, Quote, _crypto_quotes, _stooq_quote, _yahoo_quote

STOOQ_CSV = """Date,Open,High,Low,Close,Volume
2026-09-16,2410.0,2425.0,2400.0,2420.00,0
2026-09-17,2420.0,2460.0,2415.0,2457.00,0
"""

STOOQ_EMPTY = "Date,Open,High,Low,Close,Volume\n"


class FakeResponse:
    def __init__(self, text="", payload=None, status=200):
        self.text = text
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    """عميل HTTP وهمي: يعيد ردوداً محضّرة ويسجّل الطلبات."""

    def __init__(self, response):
        self._response = response
        self.calls = []

    async def get(self, url, params=None):
        self.calls.append((url, params))
        if callable(self._response):
            return self._response(url, params)
        return self._response


async def test_stooq_computes_close_to_close_change():
    client = FakeClient(FakeResponse(text=STOOQ_CSV))
    quote = await _stooq_quote(client, "xauusd", "الذهب")
    assert quote.price == 2457.00
    assert quote.change_pct == pytest.approx((2457 - 2420) / 2420 * 100)
    assert quote.as_of == "2026-09-17"
    assert quote.source == "stooq"


async def test_stooq_returns_none_when_no_data():
    client = FakeClient(FakeResponse(text=STOOQ_EMPTY))
    assert await _stooq_quote(client, "nope", "لا شيء") is None


async def test_crypto_quotes_parsed():
    payload = {
        "bitcoin": {"usd": 61234.5, "usd_24h_change": -1.23},
        "ethereum": {"usd": 2400.0, "usd_24h_change": 0.8},
    }
    client = FakeClient(FakeResponse(payload=payload))
    quotes = await _crypto_quotes(client)
    assert [q.symbol for q in quotes] == ["BTC", "ETH"]      # المفقودة تُتجاهل بهدوء
    assert quotes[0].change_pct == -1.23


async def test_yahoo_quote_uses_previous_close():
    payload = {"chart": {"result": [{"meta": {
        "regularMarketPrice": 8.0,
        "chartPreviousClose": 7.5,
        "currency": "AED",
        "regularMarketTime": 1789000000,
    }}]}}
    client = FakeClient(FakeResponse(payload=payload))
    quote = await _yahoo_quote(client, "EMAAR.AE", "إعمار")
    assert quote.price == 8.0
    assert quote.change_pct == pytest.approx(6.666, rel=1e-3)
    assert quote.currency == "AED"


async def test_yahoo_quote_handles_empty_result():
    client = FakeClient(FakeResponse(payload={"chart": {"result": []}}))
    assert await _yahoo_quote(client, "X.AE", "س") is None


async def test_snapshot_prompt_lists_groups_and_failures():
    snap = MarketSnapshot(taken_at="2026-09-20 10:00 UTC")
    snap.groups["الذهب والسلع"] = [Quote("الذهب", "XAUUSD", 2457.0, 1.5)]
    snap.groups["فاضي"] = []
    snap.errors.append("السوق الإماراتي: تعذّر جلب رمزين.")
    text = snap.to_prompt()
    assert "الذهب (XAUUSD): 2,457.00 USD | التغير: +1.50%" in text
    assert "فاضي" not in text
    assert "استخدم البحث في الإنترنت" in text
    assert not snap.is_empty()


async def test_fetch_snapshot_survives_total_network_failure(monkeypatch):
    """لو حُجبت كل المصادر، تُرجع لقطة فاضية مع تنبيه — ولا ترمي استثناء."""

    class DeadClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(market_data.httpx, "AsyncClient", lambda **kw: DeadClient())
    snap = await market_data.fetch_snapshot()
    assert snap.is_empty()
    assert any("البحث في الإنترنت" in e for e in snap.errors)


async def test_fetch_symbols_falls_back_from_stooq_to_yahoo(monkeypatch):
    def router(url, params=None):
        if "stooq" in url:
            return FakeResponse(text=STOOQ_EMPTY)
        return FakeResponse(payload={"chart": {"result": [{"meta": {
            "regularMarketPrice": 12.5, "chartPreviousClose": 12.0, "currency": "AED"}}]}})

    class Ctx(FakeClient):
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(market_data.httpx, "AsyncClient", lambda **kw: Ctx(router))
    quotes, missing = await market_data.fetch_symbols(["EMAAR.AE"])
    assert missing == []
    assert quotes[0].price == 12.5
