"""جلب أسعار السوق الحية من مصادر مجانية لا تحتاج مفاتيح.

كل مصدر معزول: لو فشل مصدر (حجب، تغيّر في الـ API، رمز خاطئ) تُسجَّل ملاحظة
في `errors` ويكمل الباقي — ولا يسقط التقرير كله. النموذج يُخبَر بما لم يتوفر
فيعوّضه بالبحث في الإنترنت بدل أن يخمّن.
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger(__name__)

STOOQ_HISTORY = "https://stooq.com/q/d/l/"
COINGECKO_PRICE = "https://api.coingecko.com/api/v3/simple/price"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

USER_AGENT = "Mozilla/5.0 (compatible; FinancialAdvisorBot/1.0)"
TIMEOUT = httpx.Timeout(15.0, connect=8.0)


@dataclass
class Quote:
    name: str
    symbol: str
    price: float
    change_pct: float | None = None
    currency: str = "USD"
    source: str = ""
    as_of: str = ""

    def line(self) -> str:
        change = "غير متاح" if self.change_pct is None else f"{self.change_pct:+.2f}%"
        price = f"{self.price:,.4f}".rstrip("0").rstrip(".") if self.price < 10 else f"{self.price:,.2f}"
        stamp = f" — {self.as_of}" if self.as_of else ""
        return f"{self.name} ({self.symbol}): {price} {self.currency} | التغير: {change}{stamp}"


@dataclass
class MarketSnapshot:
    groups: dict[str, list[Quote]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    taken_at: str = ""

    def to_prompt(self) -> str:
        """يحوّل اللقطة إلى نص يُحقن في رسالة النموذج."""
        if not self.groups and not self.errors:
            return "لا تتوفر بيانات أسعار مباشرة الآن."
        parts = [f"بيانات أسعار محدّثة (وقت السحب: {self.taken_at}):"]
        for group, quotes in self.groups.items():
            if not quotes:
                continue
            parts.append(f"\n[{group}]")
            parts.extend("  " + q.line() for q in quotes)
        if self.errors:
            parts.append("\n[مصادر لم تتوفر — استخدم البحث في الإنترنت للتحقق منها]")
            parts.extend("  " + e for e in self.errors)
        return "\n".join(parts)

    def is_empty(self) -> bool:
        return not any(self.groups.values())


# ── خريطة الرموز الافتراضية ──────────────────────────────────
# stooq: مؤشرات عالمية، معادن، طاقة، عملات.
STOOQ_UNIVERSE: dict[str, list[tuple[str, str]]] = {
    "الأسواق العالمية": [
        ("^spx", "مؤشر ستاندرد آند بورز 500"),
        ("^ndq", "مؤشر ناسداك 100"),
        ("^dji", "مؤشر داو جونز"),
        ("^dax", "مؤشر داكس الألماني"),
    ],
    "الذهب والسلع": [
        ("xauusd", "الذهب (أونصة)"),
        ("xagusd", "الفضة (أونصة)"),
        ("cl.f", "نفط خام WTI"),
        ("cb.f", "نفط برنت"),
    ],
    "العملات": [
        ("eurusd", "يورو/دولار"),
        ("usdjpy", "دولار/ين"),
        ("gbpusd", "جنيه/دولار"),
    ],
}

# coingecko: معرّفات العملات الرقمية.
CRYPTO_UNIVERSE: list[tuple[str, str, str]] = [
    ("bitcoin", "BTC", "بيتكوين"),
    ("ethereum", "ETH", "إيثيريوم"),
    ("solana", "SOL", "سولانا"),
    ("ripple", "XRP", "ريبل"),
    ("binancecoin", "BNB", "بينانس كوين"),
]

# yahoo: السوق الإماراتي (أبوظبي ودبي). الرموز قابلة للتعديل من الإعدادات.
UAE_UNIVERSE: list[tuple[str, str]] = [
    ("EMAAR.AE", "إعمار العقارية (دبي)"),
    ("DIB.AE", "بنك دبي الإسلامي"),
    ("IHC.AE", "القابضة IHC (أبوظبي)"),
    ("ADCB.AE", "بنك أبوظبي التجاري"),
]


# ── جالبو البيانات ───────────────────────────────────────────
async def _stooq_quote(client: httpx.AsyncClient, symbol: str, name: str) -> Quote | None:
    """سعر الإغلاق الأخير ونسبة التغير عن الإغلاق السابق من stooq."""
    today = datetime.now(timezone.utc).date()
    params = {
        "s": symbol,
        "i": "d",
        "d1": (today - timedelta(days=14)).strftime("%Y%m%d"),
        "d2": today.strftime("%Y%m%d"),
    }
    resp = await client.get(STOOQ_HISTORY, params=params)
    resp.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    closes = [(r.get("Date", ""), float(r["Close"])) for r in rows if r.get("Close") not in (None, "", "N/D")]
    if not closes:
        return None
    date, last = closes[-1]
    change = None
    if len(closes) >= 2 and closes[-2][1]:
        change = (last - closes[-2][1]) / closes[-2][1] * 100
    return Quote(name=name, symbol=symbol.upper(), price=last, change_pct=change,
                 source="stooq", as_of=date)


async def _crypto_quotes(client: httpx.AsyncClient) -> list[Quote]:
    ids = ",".join(cid for cid, _, _ in CRYPTO_UNIVERSE)
    resp = await client.get(
        COINGECKO_PRICE,
        params={"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true"},
    )
    resp.raise_for_status()
    data = resp.json()
    quotes: list[Quote] = []
    for coin_id, ticker, name in CRYPTO_UNIVERSE:
        entry = data.get(coin_id)
        if not entry or entry.get("usd") is None:
            continue
        quotes.append(
            Quote(
                name=name,
                symbol=ticker,
                price=float(entry["usd"]),
                change_pct=entry.get("usd_24h_change"),
                source="coingecko",
                as_of="آخر 24 ساعة",
            )
        )
    return quotes


async def _yahoo_quote(client: httpx.AsyncClient, symbol: str, name: str) -> Quote | None:
    resp = await client.get(YAHOO_CHART.format(symbol=symbol), params={"range": "5d", "interval": "1d"})
    resp.raise_for_status()
    result = (resp.json().get("chart") or {}).get("result") or []
    if not result:
        return None
    meta = result[0].get("meta") or {}
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if price is None:
        return None
    change = ((price - prev) / prev * 100) if prev else None
    stamp = ""
    if meta.get("regularMarketTime"):
        stamp = datetime.fromtimestamp(meta["regularMarketTime"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return Quote(name=name, symbol=symbol, price=float(price), change_pct=change,
                 currency=meta.get("currency", "AED"), source="yahoo", as_of=stamp)


async def _gather(label: str, coros: list, errors: list[str]) -> list[Quote]:
    """ينفّذ الطلبات بالتوازي ويتجاهل ما يفشل مع تسجيل السبب."""
    results = await asyncio.gather(*coros, return_exceptions=True)
    quotes: list[Quote] = []
    failed = 0
    for item in results:
        if isinstance(item, Exception):
            failed += 1
            log.warning("فشل جلب سعر ضمن %s: %s", label, item)
        elif isinstance(item, Quote):
            quotes.append(item)
        elif item is None:
            failed += 1
    if failed:
        errors.append(f"{label}: تعذّر جلب {failed} رمز/رموز من المصدر المباشر.")
    return quotes


async def fetch_snapshot(include_uae: bool = True) -> MarketSnapshot:
    """لقطة شاملة للأسواق التي يتابعها المستخدم."""
    snapshot = MarketSnapshot(taken_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers, follow_redirects=True) as client:
        tasks: dict[str, asyncio.Task] = {}

        for group, symbols in STOOQ_UNIVERSE.items():
            coros = [_stooq_quote(client, sym, name) for sym, name in symbols]
            tasks[group] = asyncio.create_task(_gather(group, coros, snapshot.errors))

        crypto_task = asyncio.create_task(_crypto_quotes(client))

        if include_uae:
            coros = [_yahoo_quote(client, sym, name) for sym, name in UAE_UNIVERSE]
            tasks["السوق الإماراتي"] = asyncio.create_task(_gather("السوق الإماراتي", coros, snapshot.errors))

        for group, task in tasks.items():
            snapshot.groups[group] = await task

        try:
            snapshot.groups["العملات الرقمية"] = await crypto_task
        except Exception as exc:
            log.warning("فشل جلب العملات الرقمية: %s", exc)
            snapshot.groups["العملات الرقمية"] = []
            snapshot.errors.append("العملات الرقمية: تعذّر الوصول إلى مصدر الأسعار المباشر.")

    if snapshot.is_empty():
        snapshot.errors.append(
            "لم يتوفر أي مصدر أسعار مباشر (غالباً حجب شبكة). اعتمد كلياً على البحث في الإنترنت."
        )
    return snapshot


async def fetch_symbols(symbols: list[str]) -> tuple[list[Quote], list[str]]:
    """جلب أسعار رموز محددة يطلبها المستخدم (تجربة stooq ثم yahoo)."""
    quotes: list[Quote] = []
    missing: list[str] = []
    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers, follow_redirects=True) as client:
        for raw in symbols:
            symbol = raw.strip()
            if not symbol:
                continue
            quote = None
            for fetch in (_stooq_quote, _yahoo_quote):
                try:
                    quote = await fetch(client, symbol.lower() if fetch is _stooq_quote else symbol, symbol.upper())
                except Exception as exc:  # مصدر واحد فشل — نجرّب التالي
                    log.debug("تعذّر %s للرمز %s: %s", fetch.__name__, symbol, exc)
                    quote = None
                if quote is not None:
                    break
            if quote is None:
                missing.append(symbol.upper())
            else:
                quotes.append(quote)
    return quotes, missing
