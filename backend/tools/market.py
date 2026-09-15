"""موصل بيانات السوق.

مزوّدان بلا مفاتيح يتعاقبان لكل أداة: **Stooq** (CSV بسيط) ثم
**Yahoo Finance** (JSON). سقوط أحدهما لم يعد يُعمي التاجر، ولا تُعلن
الأداة مفقودة إلا بعد فشل الاثنين.
"""
from __future__ import annotations

import asyncio
import csv
import io
import json

from ..config import settings
from ..schemas import Evidence
from .base import ConnectorResult, FailureKind, clamp, fetch

# (التسمية، رمز Stooq، رمز Yahoo)
Instrument = tuple[str, str, str]

DEFAULT_INSTRUMENTS: list[Instrument] = [
    ("S&P 500", "^spx", "^GSPC"),
    ("Nasdaq 100", "^ndq", "^NDX"),
    ("الذهب", "xauusd", "GC=F"),
    ("برنت", "cb.f", "BZ=F"),
    ("دولار/ين", "usdjpy", "JPY=X"),
    ("مؤشر الدولار", "dx.f", "DX-Y.NYB"),
    ("عائد 10 سنوات أمريكي", "10usy.b", "^TNX"),
    ("بيتكوين", "btcusd", "BTC-USD"),
]


def _evidence(label: str, source: str, url: str, close: float, open_: float,
              extra: str, stamp: str) -> Evidence:
    change = (close - open_) / open_ * 100 if open_ else 0.0
    return Evidence(
        source_type="market_data",
        title=f"{label}: إغلاق {close:g} | تغير الجلسة {change:+.2f}%",
        url=url,
        publisher=source,
        published_at=stamp,
        excerpt=extra,
        reliability=0.8,
    )


# ------------------------------------------------------------------ Stooq

async def _from_stooq(label: str, symbol: str) -> Evidence | None:
    result = await fetch(
        "https://stooq.com/q/l/",
        params={"s": symbol, "f": "sd2t2ohlcv", "h": "", "e": "csv"},
    )
    if not result.ok:
        return None

    rows = list(csv.DictReader(io.StringIO(result.text)))
    if not rows:
        return None
    row = rows[0]
    try:
        close = float(row["Close"])
        open_ = float(row["Open"])
    except (KeyError, TypeError, ValueError):
        return None

    return _evidence(
        f"{label} ({symbol})", "Stooq", f"https://stooq.com/q/?s={symbol}",
        close, open_,
        (f"افتتاح {row.get('Open')} | أعلى {row.get('High')} | "
         f"أدنى {row.get('Low')} | حجم {row.get('Volume')}"),
        f"{row.get('Date','')} {row.get('Time','')}".strip(),
    )


# ------------------------------------------------------------------ Yahoo

async def _from_yahoo(label: str, symbol: str) -> Evidence | None:
    result = await fetch(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        params={"interval": "1d", "range": "5d"},
    )
    if not result.ok:
        return None

    try:
        payload = json.loads(result.text)
        entry = payload["chart"]["result"][0]
        meta = entry["meta"]
        close = float(meta["regularMarketPrice"])
        open_ = float(meta.get("chartPreviousClose") or meta.get("previousClose") or close)
    except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError):
        return None

    quote = (entry.get("indicators", {}).get("quote") or [{}])[0]
    highs = [h for h in (quote.get("high") or []) if h is not None]
    lows = [l for l in (quote.get("low") or []) if l is not None]
    extra = (f"أعلى 5 جلسات {max(highs):g} | أدنى 5 جلسات {min(lows):g}"
             if highs and lows else f"عملة {meta.get('currency', '—')}")

    return _evidence(
        f"{label} ({symbol})", "Yahoo Finance",
        f"https://finance.yahoo.com/quote/{symbol}", close, open_, extra,
        str(meta.get("regularMarketTime", "")),
    )


async def _quote(instrument: Instrument) -> Evidence | None:
    """يجرّب المزوّدين بالترتيب — أول من يردّ ببيانات صالحة يفوز."""
    label, stooq_symbol, yahoo_symbol = instrument
    # كسول عمداً: إنشاء كوروتين المزوّد الثاني مسبقاً يُسرّبه إن نجح الأول
    for provider, symbol in ((_from_stooq, stooq_symbol), (_from_yahoo, yahoo_symbol)):
        evidence = await provider(label, symbol)
        if evidence is not None:
            return evidence
    return None


async def fetch_market_snapshot(
    instruments: list[Instrument] | None = None,
) -> ConnectorResult:
    """لقطة سوق عبر فئات الأصول الرئيسية."""
    targets = instruments or DEFAULT_INSTRUMENTS
    results = await asyncio.gather(
        *(_quote(item) for item in targets), return_exceptions=True
    )
    evidence = [r for r in results if isinstance(r, Evidence)]

    if not evidence:
        return ConnectorResult.failed(
            "market:quotes",
            f"لم يستجب أي مزوّد تسعير لأي من {len(targets)} أدوات (Stooq و Yahoo)",
            FailureKind.UNREACHABLE, attempted=len(targets) * 2,
        )

    providers = {e.publisher for e in evidence}
    return ConnectorResult(
        name="market:quotes", ok=True,
        evidence=clamp(evidence, limit=len(evidence)),
        note=(f"{len(evidence)}/{len(targets)} أداة مُسعّرة "
              f"عبر {', '.join(sorted(providers))}"),
        reached=len(evidence), attempted=len(targets),
    )


# ---------------------------------------------------------------- المطلعون

async def fetch_insider_activity(symbol: str) -> ConnectorResult:
    """تداولات المطلعين المفصح عنها.

    يفضّل Finnhub عند توفر مفتاح، ويسقط إلى خلاصة SEC EDGAR العامة
    (نموذج 4) وهي بلا مفتاح لكن بلا تصفية حسب الرمز.
    """
    if settings.finnhub_api_key:
        result = await fetch(
            "https://finnhub.io/api/v1/stock/insider-transactions",
            params={"symbol": symbol, "token": settings.finnhub_api_key},
        )
        if result.ok:
            try:
                rows = json.loads(result.text).get("data", [])
            except json.JSONDecodeError:
                rows = []
            evidence = [
                Evidence(
                    source_type="filing",
                    title=(f"{row.get('name')} — "
                           f"{'شراء' if (row.get('change') or 0) > 0 else 'بيع'} "
                           f"{abs(row.get('change') or 0)} سهم من {symbol}"),
                    publisher="Finnhub / إفصاحات المطلعين",
                    published_at=row.get("transactionDate"),
                    excerpt=f"السعر {row.get('transactionPrice')} | الرمز {row.get('transactionCode')}",
                    reliability=0.9,
                )
                for row in rows[: settings.max_evidence_per_tool]
            ]
            if evidence:
                return ConnectorResult(
                    name="market:insider", ok=True, evidence=evidence,
                    note=f"{len(evidence)} إفصاحاً لـ {symbol}", reached=1, attempted=1,
                )

    return await _edgar_form4(symbol)


async def _edgar_form4(symbol: str) -> ConnectorResult:
    """أحدث نماذج 4 من EDGAR — بلا مفتاح، عامة لكل السوق لا لرمز بعينه."""
    result = await fetch(
        "https://www.sec.gov/cgi-bin/browse-edgar",
        params={"action": "getcompany", "type": "4", "dateb": "", "owner": "include",
                "count": "20", "output": "atom"},
    )
    if not result.ok:
        hint = ("FINNHUB_API_KEY غير مضبوط، و" if not settings.finnhub_api_key else "")
        return ConnectorResult.failed(
            "market:insider", f"{hint}تعذّر الوصول إلى EDGAR: {result.detail}",
            result.kind or FailureKind.UNREACHABLE, attempted=2,
        )

    from .news import _parse_feed   # إعادة استخدام محلل الخلاصات

    evidence = _parse_feed(result.text, "SEC EDGAR — نموذج 4", 0.95)
    if not evidence:
        return ConnectorResult.failed(
            "market:insider", "لا إفصاحات حديثة في خلاصة EDGAR",
            FailureKind.EMPTY, attempted=2,
        )
    return ConnectorResult(
        name="market:insider", ok=True, evidence=clamp(evidence),
        note=(f"{len(evidence)} إفصاحاً عاماً من EDGAR — غير مُصفّى حسب {symbol}؛ "
              "اضبط FINNHUB_API_KEY للتصفية حسب الرمز"),
        reached=1, attempted=2,
    )
