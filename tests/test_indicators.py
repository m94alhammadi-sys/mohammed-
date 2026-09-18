"""اختبارات المؤشرات الفنية — قيم معروفة ومنطق حدودي."""

import numpy as np
import pandas as pd
import pytest

from app.market import indicators as ta


def test_rsi_all_gains_is_100():
    """سلسلة صاعدة بلا خسائر = RSI عند 100."""
    series = pd.Series(range(1, 60), dtype=float)
    assert ta.rsi(series).iloc[-1] == pytest.approx(100.0)


def test_rsi_all_losses_near_zero():
    series = pd.Series(range(60, 1, -1), dtype=float)
    assert ta.rsi(series).iloc[-1] == pytest.approx(0.0, abs=1e-6)


def test_rsi_bounds():
    rng = np.random.default_rng(0)
    series = pd.Series(100 + rng.normal(0, 1, 300).cumsum())
    values = ta.rsi(series).dropna()
    assert values.between(0, 100).all()


def test_sma_matches_manual_mean():
    series = pd.Series([1, 2, 3, 4, 5], dtype=float)
    assert ta.sma(series, 3).iloc[-1] == pytest.approx(4.0)
    assert pd.isna(ta.sma(series, 3).iloc[1])          # قبل اكتمال النافذة


def test_macd_histogram_is_difference():
    series = pd.Series(100 + np.sin(np.linspace(0, 20, 200)) * 10)
    macd_line, signal_line, hist = ta.macd(series)
    assert hist.iloc[-1] == pytest.approx(macd_line.iloc[-1] - signal_line.iloc[-1])


def test_bollinger_bands_ordered():
    rng = np.random.default_rng(1)
    series = pd.Series(100 + rng.normal(0, 2, 200).cumsum())
    upper, middle, lower = ta.bollinger(series)
    assert upper.iloc[-1] > middle.iloc[-1] > lower.iloc[-1]


def test_atr_is_positive():
    rng = np.random.default_rng(2)
    close = pd.Series(100 + rng.normal(0, 1, 200).cumsum())
    high, low = close + 1, close - 1
    assert ta.atr(high, low, close).iloc[-1] > 0


def test_adx_strong_trend_above_weak_trend():
    """اتجاه نظيف يجب أن يعطي ADX أعلى من سوق عشوائي."""
    n = 300
    trend_close = pd.Series(np.arange(n, dtype=float) + 100)
    trend_adx = ta.adx(trend_close + 0.5, trend_close - 0.5, trend_close)[0].iloc[-1]

    rng = np.random.default_rng(3)
    flat_close = pd.Series(100 + rng.normal(0, 1, n))
    flat_adx = ta.adx(flat_close + 0.5, flat_close - 0.5, flat_close)[0].iloc[-1]

    assert trend_adx > flat_adx


def test_pivot_levels_ordering():
    levels = ta.pivot_levels(110, 100, 105)
    assert levels["s3"] < levels["s2"] < levels["s1"] < levels["pivot"]
    assert levels["pivot"] < levels["r1"] < levels["r2"] < levels["r3"]


def test_fibonacci_levels_descend():
    fib = ta.fibonacci_retracement(200, 100)
    assert fib["0.0%"] == 200 and fib["100.0%"] == 100
    assert fib["50.0%"] == pytest.approx(150)
    values = list(fib.values())
    assert values == sorted(values, reverse=True)


def test_cluster_merges_close_levels():
    merged = ta._cluster([10.00, 10.05, 20.0, 20.1, 50.0])
    assert len(merged) == 3


def test_stochastic_bounds():
    rng = np.random.default_rng(4)
    close = pd.Series(100 + rng.normal(0, 2, 200).cumsum())
    k, d = ta.stochastic(close + 1, close - 1, close)
    assert k.dropna().between(0, 100).all()
    assert d.dropna().between(0, 100).all()
