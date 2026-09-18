"""جلب بيانات الأسواق من Yahoo Finance مع تخزين مؤقت وتجربة رموز بديلة."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import pandas as pd

from .symbols import CATALOG, SymbolInfo, describe, to_ticker

log = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_LOCK = threading.RLock()
_RESOLVED: dict[str, str] = {}   # رمز مطلوب -> رمز نجح فعلياً

# مدة صلاحية الكاش بالثواني حسب الفاصل الزمني
_TTL = {"1m": 60, "5m": 120, "15m": 300, "30m": 600, "60m": 900, "1h": 900, "1d": 900, "1wk": 3600}


class MarketDataError(RuntimeError):
    """فشل جلب البيانات من المصدر."""


def _cache_get(key: str, ttl: int) -> Any | None:
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if entry and time.time() - entry[0] < ttl:
            return entry[1]
    return None


def _cache_put(key: str, value: Any) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), value)
        if len(_CACHE) > 500:               # تنظيف بسيط
            oldest = sorted(_CACHE.items(), key=lambda kv: kv[1][0])[:100]
            for k, _ in oldest:
                _CACHE.pop(k, None)


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def _candidates(ticker: str) -> list[str]:
    """الرمز الأساسي + البدائل (لاحقات .AD/.DU/.AE تختلف بين المصادر)."""
    ticker = ticker.upper()
    if ticker in _RESOLVED:
        return [_RESOLVED[ticker]]
    info: SymbolInfo | None = CATALOG.get(ticker)
    out = [ticker]
    if info:
        out += [f for f in info.fallbacks if f not in out]
    return out


def _fetch_raw(ticker: str, period: str, interval: str) -> pd.DataFrame:
    import yfinance as yf

    frame = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
    if frame is None or frame.empty:
        return pd.DataFrame()
    frame = frame.rename(columns=str.title)
    needed = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in needed if c not in frame.columns]
    if missing:
        return pd.DataFrame()
    return frame[needed].dropna(subset=["Close"])


def get_history(symbol: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    """يجلب الشموع التاريخية. ``symbol`` قد يكون اسماً عربياً أو رمزاً."""
    ticker = to_ticker(symbol)
    key = f"hist:{ticker}:{period}:{interval}"
    cached = _cache_get(key, _TTL.get(interval, 900))
    if cached is not None:
        return cached

    last_error: Exception | None = None
    for candidate in _candidates(ticker):
        try:
            frame = _fetch_raw(candidate, period, interval)
        except Exception as exc:                      # مشاكل شبكة أو رمز غير صالح
            last_error = exc
            log.warning("فشل جلب %s: %s", candidate, exc)
            continue
        if not frame.empty:
            _RESOLVED[ticker] = candidate
            _cache_put(key, frame)
            return frame

    if last_error:
        raise MarketDataError(f"تعذّر جلب بيانات {describe(ticker)}: {last_error}")
    raise MarketDataError(f"لا توجد بيانات متاحة للرمز {describe(ticker)}")


@dataclass
class Quote:
    symbol: str
    name_ar: str
    market: str
    currency: str
    price: float
    previous_close: float
    change: float
    change_pct: float
    day_high: float
    day_low: float
    volume: float
    avg_volume_20d: float
    week52_high: float
    week52_low: float
    as_of: str

    def to_dict(self) -> dict:
        return {
            "الرمز": self.symbol,
            "الاسم": self.name_ar,
            "السوق": self.market,
            "العملة": self.currency,
            "السعر": round(self.price, 4),
            "الإغلاق_السابق": round(self.previous_close, 4),
            "التغير": round(self.change, 4),
            "التغير_نسبة_مئوية": round(self.change_pct, 2),
            "أعلى_اليوم": round(self.day_high, 4),
            "أدنى_اليوم": round(self.day_low, 4),
            "الحجم": int(self.volume) if self.volume == self.volume else 0,
            "متوسط_الحجم_20_يوم": int(self.avg_volume_20d) if self.avg_volume_20d == self.avg_volume_20d else 0,
            "أعلى_52_أسبوع": round(self.week52_high, 4),
            "أدنى_52_أسبوع": round(self.week52_low, 4),
            "آخر_تحديث": self.as_of,
        }


def get_quote(symbol: str) -> Quote:
    """سعر لحظي (أو آخر إغلاق) مع سياق اليوم والمدى السنوي."""
    ticker = to_ticker(symbol)
    frame = get_history(ticker, period="1y", interval="1d")
    if len(frame) < 2:
        raise MarketDataError(f"بيانات غير كافية للرمز {describe(ticker)}")

    last = frame.iloc[-1]
    prev = frame.iloc[-2]
    price = float(last["Close"])
    previous_close = float(prev["Close"])
    change = price - previous_close
    info = CATALOG.get(ticker)

    return Quote(
        symbol=ticker,
        name_ar=info.ar if info else ticker,
        market=info.market if info else "—",
        currency=info.currency if info else "USD",
        price=price,
        previous_close=previous_close,
        change=change,
        change_pct=(change / previous_close * 100) if previous_close else 0.0,
        day_high=float(last["High"]),
        day_low=float(last["Low"]),
        volume=float(last["Volume"]),
        avg_volume_20d=float(frame["Volume"].tail(20).mean()),
        week52_high=float(frame["High"].tail(252).max()),
        week52_low=float(frame["Low"].tail(252).min()),
        as_of=str(frame.index[-1].date()),
    )


def get_quotes(symbols: list[str]) -> list[dict]:
    """أسعار عدة رموز دفعة واحدة — يتجاهل ما يفشل بدل أن يتوقف."""
    out: list[dict] = []
    for symbol in symbols:
        try:
            out.append(get_quote(symbol).to_dict())
        except Exception as exc:
            out.append({"الرمز": to_ticker(symbol), "خطأ": str(exc)})
    return out


def performance(symbol: str) -> dict:
    """عوائد الرمز عبر فترات مختلفة — لقياس الزخم النسبي."""
    frame = get_history(symbol, period="2y", interval="1d")
    close = frame["Close"]
    latest = float(close.iloc[-1])

    def ret(days: int) -> float | None:
        if len(close) <= days:
            return None
        past = float(close.iloc[-(days + 1)])
        return round((latest / past - 1) * 100, 2) if past else None

    ytd = None
    this_year = close[close.index.year == close.index[-1].year]
    if len(this_year) > 1:
        ytd = round((latest / float(this_year.iloc[0]) - 1) * 100, 2)

    return {
        "الرمز": to_ticker(symbol),
        "يوم": ret(1),
        "أسبوع": ret(5),
        "شهر": ret(21),
        "3_أشهر": ret(63),
        "6_أشهر": ret(126),
        "سنة": ret(252),
        "منذ_بداية_العام": ytd,
    }


def correlation(symbols: list[str], period: str = "6mo") -> dict:
    """مصفوفة الارتباط بين عدة أصول — مهمة لتنويع المحفظة."""
    closes: dict[str, pd.Series] = {}
    for symbol in symbols:
        try:
            closes[to_ticker(symbol)] = get_history(symbol, period=period)["Close"]
        except Exception as exc:
            log.warning("تخطي %s في حساب الارتباط: %s", symbol, exc)
    if len(closes) < 2:
        return {"خطأ": "أحتاج رمزين صالحين على الأقل لحساب الارتباط"}

    matrix = pd.DataFrame(closes).pct_change(fill_method=None).dropna().corr()
    return {
        "الفترة": period,
        "المصفوفة": {
            row: {col: round(float(matrix.loc[row, col]), 2) for col in matrix.columns}
            for row in matrix.index
        },
    }
