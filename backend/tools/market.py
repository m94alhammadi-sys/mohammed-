"""موصل بيانات السوق: أسعار وإغلاقات يومية بلا مفاتيح (Stooq)،
مع مسار اختياري لـ Finnhub عند توفر مفتاح."""
from __future__ import annotations

import asyncio
import csv
import io

from ..config import settings
from ..schemas import Evidence
from .base import ConnectorResult, clamp, http_get

# رموز افتراضية تغطي فئات الأصول الرئيسية على Stooq.
DEFAULT_SYMBOLS: dict[str, str] = {
    "S&P 500": "^spx",
    "Nasdaq 100": "^ndq",
    "الذهب": "xauusd",
    "برنت": "cb.f",
    "دولار/ين": "usdjpy",
    "مؤشر الدولار": "dx.f",
    "عائد 10 سنوات أمريكي": "10usy.b",
    "بيتكوين": "btcusd",
}


def _parse_stooq(csv_text: str) -> dict[str, str] | None:
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    if not rows:
        return None
    row = rows[0]
    if row.get("Close") in (None, "", "N/D"):
        return None
    return row


async def _quote(label: str, symbol: str) -> Evidence | None:
    response = await http_get(
        "https://stooq.com/q/l/", params={"s": symbol, "f": "sd2t2ohlcv", "h": "", "e": "csv"}
    )
    if response is None:
        return None
    row = _parse_stooq(response.text)
    if row is None:
        return None

    try:
        close = float(row["Close"])
        open_ = float(row["Open"])
        change = (close - open_) / open_ * 100 if open_ else 0.0
    except (KeyError, ValueError):
        return None

    return Evidence(
        source_type="market_data",
        title=f"{label} ({symbol}): إغلاق {close:g} | تغير الجلسة {change:+.2f}%",
        url=f"https://stooq.com/q/?s={symbol}",
        publisher="Stooq",
        published_at=f"{row.get('Date','')} {row.get('Time','')}".strip(),
        excerpt=(f"افتتاح {row.get('Open')} | أعلى {row.get('High')} | "
                 f"أدنى {row.get('Low')} | حجم {row.get('Volume')}"),
        reliability=0.8,
    )


async def fetch_market_snapshot(symbols: dict[str, str] | None = None) -> ConnectorResult:
    """لقطة سوق عبر فئات الأصول الرئيسية."""
    targets = symbols or DEFAULT_SYMBOLS
    results = await asyncio.gather(
        *(_quote(label, sym) for label, sym in targets.items()), return_exceptions=True
    )
    evidence = [r for r in results if isinstance(r, Evidence)]
    if not evidence:
        return ConnectorResult.failed(
            "market:stooq", "تعذّر جلب أي تسعيرة سوق (شبكة محجوبة أو المصدر لا يستجيب)"
        )
    return ConnectorResult(
        name="market:stooq", ok=True, evidence=clamp(evidence, limit=len(evidence)),
        note=f"{len(evidence)}/{len(targets)} أداة تم تسعيرها",
    )


async def fetch_insider_activity(symbol: str) -> ConnectorResult:
    """تداولات المطلعين المفصح عنها (يتطلب مفتاح Finnhub)."""
    if not settings.finnhub_api_key:
        return ConnectorResult.failed(
            "market:insider", "FINNHUB_API_KEY غير مضبوط — بيانات المطلعين غير متاحة"
        )
    response = await http_get(
        "https://finnhub.io/api/v1/stock/insider-transactions",
        params={"symbol": symbol, "token": settings.finnhub_api_key},
    )
    if response is None:
        return ConnectorResult.failed("market:insider", "لم يستجب Finnhub")

    data = response.json().get("data", [])
    evidence = [
        Evidence(
            source_type="filing",
            title=(f"{row.get('name')} — {'شراء' if (row.get('change') or 0) > 0 else 'بيع'} "
                   f"{abs(row.get('change') or 0)} سهم من {symbol}"),
            publisher="Finnhub / إفصاحات المطلعين",
            published_at=row.get("transactionDate"),
            excerpt=f"السعر {row.get('transactionPrice')} | الرمز {row.get('transactionCode')}",
            reliability=0.9,
        )
        for row in data[: settings.max_evidence_per_tool]
    ]
    if not evidence:
        return ConnectorResult.failed("market:insider", f"لا إفصاحات حديثة لـ {symbol}")
    return ConnectorResult(name="market:insider", ok=True, evidence=evidence)
