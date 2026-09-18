"""مؤشرات التحليل الفني — تنفيذ خالص بـ pandas/numpy (بدون TA-Lib)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """مؤشر القوة النسبية بطريقة Wilder."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    # خسائر صفرية = قوة شرائية مطلقة
    return out.where(avg_loss != 0, 100.0)


def macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """يعيد (خط الماكد، خط الإشارة، الهيستوغرام)."""
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return macd_line, signal_line, macd_line - signal_line


def bollinger(
    series: pd.Series, period: int = 20, std_mult: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """يعيد (الحد العلوي، المتوسط، الحد السفلي)."""
    middle = sma(series, period)
    std = series.rolling(window=period, min_periods=period).std(ddof=0)
    return middle + std_mult * std, middle, middle - std_mult * std


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    return pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """متوسط المدى الحقيقي — مقياس التقلب، يُستخدم لتحديد وقف الخسارة."""
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def stochastic(
    high: pd.Series, low: pd.Series, close: pd.Series, k_period: int = 14, d_period: int = 3
) -> tuple[pd.Series, pd.Series]:
    """مذبذب ستوكاستيك: يعيد (%K, %D)."""
    lowest = low.rolling(window=k_period, min_periods=k_period).min()
    highest = high.rolling(window=k_period, min_periods=k_period).max()
    span = (highest - lowest).replace(0, np.nan)
    k = 100 * (close - lowest) / span
    return k, k.rolling(window=d_period, min_periods=d_period).mean()


def adx(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """مؤشر الاتجاه المتوسط: يعيد (ADX, +DI, -DI). ADX > 25 يعني اتجاه قوي."""
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index
    )

    atr_ = true_range(high, low, close).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    safe_atr = atr_.replace(0, np.nan)

    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / safe_atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / safe_atr

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_line = dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return adx_line, plus_di, minus_di


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """حجم التداول التراكمي — يكشف هل الحجم يدعم الحركة."""
    direction = np.sign(close.diff().fillna(0.0))
    return (direction * volume.fillna(0.0)).cumsum()


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    """السعر المرجّح بالحجم (تراكمي على النطاق المعطى)."""
    typical = (high + low + close) / 3
    vol = volume.fillna(0.0)
    cum_vol = vol.cumsum().replace(0, np.nan)
    return (typical * vol).cumsum() / cum_vol


def pivot_levels(high: float, low: float, close: float) -> dict[str, float]:
    """نقاط الارتكاز الكلاسيكية — مستويات دعم ومقاومة لليوم التالي."""
    pivot = (high + low + close) / 3
    return {
        "pivot": pivot,
        "r1": 2 * pivot - low,
        "r2": pivot + (high - low),
        "r3": high + 2 * (pivot - low),
        "s1": 2 * pivot - high,
        "s2": pivot - (high - low),
        "s3": low - 2 * (high - pivot),
    }


def swing_levels(
    high: pd.Series, low: pd.Series, lookback: int = 60, window: int = 5
) -> tuple[list[float], list[float]]:
    """يستخرج قمم وقيعان محورية (fractals) كمقاومات ودعوم فعلية."""
    highs = high.tail(lookback)
    lows = low.tail(lookback)
    resistances: list[float] = []
    supports: list[float] = []

    for i in range(window, len(highs) - window):
        segment = highs.iloc[i - window : i + window + 1]
        if highs.iloc[i] == segment.max():
            resistances.append(float(highs.iloc[i]))
    for i in range(window, len(lows) - window):
        segment = lows.iloc[i - window : i + window + 1]
        if lows.iloc[i] == segment.min():
            supports.append(float(lows.iloc[i]))

    return _cluster(supports), _cluster(resistances)


def _cluster(levels: list[float], tolerance: float = 0.01) -> list[float]:
    """يدمج المستويات المتقاربة (خلال 1%) في مستوى واحد."""
    if not levels:
        return []
    ordered = sorted(levels)
    groups: list[list[float]] = [[ordered[0]]]
    for level in ordered[1:]:
        if abs(level - groups[-1][-1]) / max(abs(groups[-1][-1]), 1e-9) <= tolerance:
            groups[-1].append(level)
        else:
            groups.append([level])
    return [round(sum(g) / len(g), 6) for g in groups]


def fibonacci_retracement(swing_high: float, swing_low: float) -> dict[str, float]:
    """مستويات تصحيح فيبوناتشي بين قمة وقاع."""
    diff = swing_high - swing_low
    return {
        "0.0%": swing_high,
        "23.6%": swing_high - 0.236 * diff,
        "38.2%": swing_high - 0.382 * diff,
        "50.0%": swing_high - 0.500 * diff,
        "61.8%": swing_high - 0.618 * diff,
        "78.6%": swing_high - 0.786 * diff,
        "100.0%": swing_low,
    }
