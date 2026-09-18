"""محرك التحليل: يحوّل الشموع إلى قراءة فنية كاملة + درجة قوة الإشارة."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from . import indicators as ta
from .data import MarketDataError, get_history, get_quote
from .symbols import CATALOG, to_ticker

Direction = Literal["صاعد", "هابط", "محايد"]


@dataclass
class Signal:
    name: str
    direction: Direction
    weight: float          # 0..3 — قوة الإشارة
    detail: str

    def to_dict(self) -> dict:
        return {"الإشارة": self.name, "الاتجاه": self.direction, "القوة": self.weight, "الشرح": self.detail}


@dataclass
class Analysis:
    symbol: str
    name_ar: str
    interval: str
    price: float
    currency: str
    score: float                       # 0 = هبوط قوي، 50 = محايد، 100 = صعود قوي
    bias: str
    signals: list[Signal] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    levels: dict = field(default_factory=dict)
    setup: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "الرمز": self.symbol,
            "الاسم": self.name_ar,
            "الفاصل_الزمني": self.interval,
            "السعر": round(self.price, 4),
            "العملة": self.currency,
            "درجة_القوة": round(self.score, 1),
            "الانحياز": self.bias,
            "المؤشرات": self.metrics,
            "المستويات": self.levels,
            "الإشارات": [s.to_dict() for s in self.signals],
            "سيناريو_مقترح": self.setup,
            "تنبيهات": self.warnings,
        }


def _safe(value) -> float | None:
    """يحوّل قيمة pandas إلى float، أو None لو NaN."""
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(val) or math.isinf(val) else val


def _bias_label(score: float) -> str:
    if score >= 75:
        return "صاعد قوي"
    if score >= 60:
        return "صاعد"
    if score > 40:
        return "محايد / عرضي"
    if score > 25:
        return "هابط"
    return "هابط قوي"


def _rsi_divergence(close: pd.Series, rsi_series: pd.Series, lookback: int = 40) -> Signal | None:
    """انفراج إيجابي/سلبي بين السعر ومؤشر RSI — من أقوى إشارات الانعكاس."""
    if len(close) < lookback + 5:
        return None
    price = close.tail(lookback)
    momentum = rsi_series.tail(lookback)
    if momentum.isna().all():
        return None

    half = lookback // 2
    p_low_1, p_low_2 = price.iloc[:half].min(), price.iloc[half:].min()
    r_low_1 = _safe(momentum.loc[price.iloc[:half].idxmin()])
    r_low_2 = _safe(momentum.loc[price.iloc[half:].idxmin()])

    p_high_1, p_high_2 = price.iloc[:half].max(), price.iloc[half:].max()
    r_high_1 = _safe(momentum.loc[price.iloc[:half].idxmax()])
    r_high_2 = _safe(momentum.loc[price.iloc[half:].idxmax()])

    if None in (r_low_1, r_low_2, r_high_1, r_high_2):
        return None

    if p_low_2 < p_low_1 and r_low_2 > r_low_1 + 2:
        return Signal(
            "انفراج إيجابي (RSI)", "صاعد", 2.5,
            f"السعر صنع قاعاً أدنى ({p_low_2:.4g}) بينما RSI صنع قاعاً أعلى — ضعف في ضغط البيع",
        )
    if p_high_2 > p_high_1 and r_high_2 < r_high_1 - 2:
        return Signal(
            "انفراج سلبي (RSI)", "هابط", 2.5,
            f"السعر صنع قمة أعلى ({p_high_2:.4g}) بينما RSI صنع قمة أدنى — تلاشي الزخم الشرائي",
        )
    return None


# إشارات ارتداد: قوتها الحقيقية في الأسواق العرضية، وتضعف داخل اتجاه مؤكد
_MEAN_REVERSION = {
    "تشبع بيعي (RSI)",
    "تشبع شرائي (RSI)",
    "لمس الحد السفلي لبولنجر",
    "لمس الحد العلوي لبولنجر",
    "انفراج إيجابي (RSI)",
    "انفراج سلبي (RSI)",
}

# الحد الأدنى لأهمية إشارة الماكد: نسبة من السعر. ما دونه ضجيج رقمي لا معنى له
_MACD_NOISE_FLOOR = 0.0005


def _apply_trend_context(
    signals: list[Signal], adx_v: float | None, plus_di: float | None, minus_di: float | None
) -> list[Signal]:
    """يخفض وزن إشارات الارتداد العكسية داخل اتجاه قوي.

    "تشبع بيعي" وسط هبوط مؤكد ليس إشارة شراء — السعر يبقى متشبعاً بيعياً طوال
    الاتجاه. نحتفظ بالإشارة كملاحظة لكن بوزن أقل حتى لا تلغي قراءة الاتجاه.
    """
    if None in (adx_v, plus_di, minus_di) or adx_v < 25:
        return signals

    trend_up = plus_di > minus_di
    counter = "صاعد" if not trend_up else "هابط"
    adjusted: list[Signal] = []
    for sig in signals:
        if sig.name in _MEAN_REVERSION and sig.direction == counter:
            adjusted.append(
                Signal(
                    sig.name,
                    sig.direction,
                    round(sig.weight * 0.4, 2),
                    sig.detail + " — لكن وزنها مخفّض لأنها تعاكس اتجاهاً مؤكداً (ADX ≥ 25)",
                )
            )
        else:
            adjusted.append(sig)
    return adjusted


def _build_signals(frame: pd.DataFrame, m: dict) -> list[Signal]:
    close = frame["Close"]
    signals: list[Signal] = []

    price = m["السعر"]
    ema20, ema50, ema200 = m.get("EMA20"), m.get("EMA50"), m.get("EMA200")
    rsi_v, macd_hist = m.get("RSI"), m.get("MACD_هيستوغرام")
    adx_v, plus_di, minus_di = m.get("ADX"), m.get("+DI"), m.get("-DI")

    # 1) هيكل الاتجاه عبر المتوسطات
    if None not in (ema50, ema200):
        if price > ema50 > ema200:
            signals.append(Signal("ترتيب صاعد للمتوسطات", "صاعد", 2.0,
                                  "السعر فوق EMA50 وهو فوق EMA200 — اتجاه صاعد سليم"))
        elif price < ema50 < ema200:
            signals.append(Signal("ترتيب هابط للمتوسطات", "هابط", 2.0,
                                  "السعر تحت EMA50 وهو تحت EMA200 — اتجاه هابط سليم"))

    # 2) تقاطع ذهبي/موت حديث
    ema50_s, ema200_s = ta.ema(close, 50), ta.ema(close, 200)
    if len(close) > 205 and not ema200_s.tail(6).isna().any():
        diff = ema50_s - ema200_s
        recent = diff.tail(6).dropna()
        if len(recent) >= 2 and recent.iloc[0] < 0 < recent.iloc[-1]:
            signals.append(Signal("تقاطع ذهبي", "صاعد", 2.5, "EMA50 اخترق EMA200 صعوداً خلال آخر جلسات"))
        elif len(recent) >= 2 and recent.iloc[0] > 0 > recent.iloc[-1]:
            signals.append(Signal("تقاطع الموت", "هابط", 2.5, "EMA50 كسر EMA200 هبوطاً خلال آخر جلسات"))

    # 3) القوة النسبية
    if rsi_v is not None:
        if rsi_v < 30:
            signals.append(Signal("تشبع بيعي (RSI)", "صاعد", 1.8,
                                  f"RSI = {rsi_v:.1f} أقل من 30 — منطقة ارتداد محتملة"))
        elif rsi_v > 70:
            signals.append(Signal("تشبع شرائي (RSI)", "هابط", 1.8,
                                  f"RSI = {rsi_v:.1f} أعلى من 70 — خطر جني أرباح"))
        elif 50 < rsi_v <= 65:
            signals.append(Signal("زخم إيجابي (RSI)", "صاعد", 1.0,
                                  f"RSI = {rsi_v:.1f} في النطاق الصاعد الصحي"))
        elif 35 <= rsi_v < 50:
            signals.append(Signal("زخم سلبي (RSI)", "هابط", 1.0, f"RSI = {rsi_v:.1f} تحت مستوى 50"))

    # 4) الماكد
    macd_line, signal_line, hist = ta.macd(close)
    hist_tail = hist.dropna().tail(3)
    # الهيستوغرام قيمة مطلقة، فنقيسها نسبةً للسعر حتى لا نطلق إشارة على ضجيج
    significant = macd_hist is not None and abs(macd_hist) > price * _MACD_NOISE_FLOOR
    if significant and len(hist_tail) >= 2:
        if hist_tail.iloc[-2] <= 0 < hist_tail.iloc[-1]:
            signals.append(Signal("تقاطع ماكد إيجابي", "صاعد", 2.0, "الهيستوغرام عبر الصفر صعوداً"))
        elif hist_tail.iloc[-2] >= 0 > hist_tail.iloc[-1]:
            signals.append(Signal("تقاطع ماكد سلبي", "هابط", 2.0, "الهيستوغرام عبر الصفر هبوطاً"))
        elif macd_hist > 0 and hist_tail.iloc[-1] > hist_tail.iloc[-2]:
            signals.append(Signal("تسارع الزخم", "صاعد", 1.0, "الهيستوغرام موجب ويتوسع"))
        elif macd_hist < 0 and hist_tail.iloc[-1] < hist_tail.iloc[-2]:
            signals.append(Signal("تسارع هبوطي", "هابط", 1.0, "الهيستوغرام سالب ويتوسع"))

    # 5) بولنجر
    bb_up, bb_low = m.get("بولنجر_علوي"), m.get("بولنجر_سفلي")
    if None not in (bb_up, bb_low):
        if price <= bb_low:
            signals.append(Signal("لمس الحد السفلي لبولنجر", "صاعد", 1.5,
                                  "السعر عند/تحت الحد السفلي — امتداد مبالغ فيه"))
        elif price >= bb_up:
            signals.append(Signal("لمس الحد العلوي لبولنجر", "هابط", 1.5,
                                  "السعر عند/فوق الحد العلوي — امتداد مبالغ فيه"))

    # 6) الانضغاط (squeeze) — تمهيد لحركة قوية
    if m.get("انضغاط_بولنجر"):
        signals.append(Signal("انضغاط بولنجر", "محايد", 1.0,
                              "النطاق في أضيق مستوياته — يسبق عادةً حركة قوية باتجاه الاختراق"))

    # 7) قوة الاتجاه
    if None not in (adx_v, plus_di, minus_di) and adx_v >= 25:
        if plus_di > minus_di:
            signals.append(Signal("اتجاه صاعد مؤكد (ADX)", "صاعد", 1.5,
                                  f"ADX = {adx_v:.1f} مع +DI فوق -DI"))
        else:
            signals.append(Signal("اتجاه هابط مؤكد (ADX)", "هابط", 1.5,
                                  f"ADX = {adx_v:.1f} مع -DI فوق +DI"))
    elif adx_v is not None and adx_v < 20:
        signals.append(Signal("سوق عرضي", "محايد", 0.8, f"ADX = {adx_v:.1f} — لا يوجد اتجاه واضح"))

    # 8) الحجم
    vol_ratio = m.get("نسبة_الحجم_للمتوسط")
    change_pct = m.get("تغير_الجلسة_%")
    if vol_ratio and vol_ratio >= 1.8 and change_pct is not None:
        if change_pct > 0:
            signals.append(Signal("حجم شرائي استثنائي", "صاعد", 1.8,
                                  f"الحجم {vol_ratio:.1f}× المتوسط مع إغلاق أخضر — دخول سيولة"))
        elif change_pct < 0:
            signals.append(Signal("حجم بيعي استثنائي", "هابط", 1.8,
                                  f"الحجم {vol_ratio:.1f}× المتوسط مع إغلاق أحمر — خروج سيولة"))

    # 9) الانفراج
    divergence = _rsi_divergence(close, ta.rsi(close))
    if divergence:
        signals.append(divergence)

    # 10) القرب من القمم/القيعان السنوية
    hi52, lo52 = m.get("أعلى_52"), m.get("أدنى_52")
    if hi52 and price >= hi52 * 0.995:
        signals.append(Signal("اختراق قمة سنوية", "صاعد", 2.0, "السعر عند أعلى مستوى في 52 أسبوعاً"))
    if lo52 and price <= lo52 * 1.005:
        signals.append(Signal("كسر قاع سنوي", "هابط", 2.0, "السعر عند أدنى مستوى في 52 أسبوعاً"))

    return _apply_trend_context(signals, adx_v, plus_di, minus_di)


def _score(signals: list[Signal]) -> float:
    """يحوّل الإشارات إلى درجة 0-100 (50 = محايد)."""
    bull = sum(s.weight for s in signals if s.direction == "صاعد")
    bear = sum(s.weight for s in signals if s.direction == "هابط")
    total = bull + bear
    if total == 0:
        return 50.0
    # التطبيع: كلما زاد الفارق النسبي ابتعدنا عن 50، مع تعزيز حسب عدد الإشارات
    net = (bull - bear) / total
    confidence = min(total / 8.0, 1.0)     # 8 نقاط وزن = ثقة كاملة
    return round(50 + net * confidence * 50, 1)


def _trade_setup(price: float, atr_v: float | None, score: float, levels: dict) -> dict:
    """سيناريو تداول تقريبي مبني على ATR والمستويات — للتوضيح لا للتنفيذ الأعمى."""
    if not atr_v or atr_v <= 0:
        return {}

    supports = levels.get("دعوم") or []
    resistances = levels.get("مقاومات") or []

    if score >= 60:
        stop = min([s for s in supports if s < price], default=price - 1.5 * atr_v)
        stop = max(stop, price - 3 * atr_v)
        risk = price - stop
        targets = [r for r in resistances if r > price][:2]
        if not targets:
            targets = [price + 2 * risk, price + 3 * risk]
        return {
            "الاتجاه": "شراء",
            "الدخول_المقترح": round(price, 4),
            "وقف_الخسارة": round(stop, 4),
            "الأهداف": [round(t, 4) for t in targets],
            "المخاطرة_للعائد": round((targets[0] - price) / risk, 2) if risk > 0 else None,
            "المخاطرة_%": round(risk / price * 100, 2) if price else None,
        }

    if score <= 40:
        stop = max([r for r in resistances if r > price], default=price + 1.5 * atr_v)
        stop = min(stop, price + 3 * atr_v)
        risk = stop - price
        targets = [s for s in sorted(supports, reverse=True) if s < price][:2]
        if not targets:
            targets = [price - 2 * risk, price - 3 * risk]
        return {
            "الاتجاه": "بيع / تقليص",
            "الدخول_المقترح": round(price, 4),
            "وقف_الخسارة": round(stop, 4),
            "الأهداف": [round(t, 4) for t in targets],
            "المخاطرة_للعائد": round((price - targets[0]) / risk, 2) if risk > 0 else None,
            "المخاطرة_%": round(risk / price * 100, 2) if price else None,
        }

    return {"الاتجاه": "انتظار", "ملاحظة": "الإشارات متعارضة — الأفضل انتظار وضوح الاتجاه"}


def analyze_frame(symbol: str, frame: pd.DataFrame, interval: str = "1d") -> Analysis:
    """يحلل شموعاً جاهزة — مفصول عن الجلب ليكون قابلاً للاختبار بدون إنترنت."""
    ticker = to_ticker(symbol)
    info = CATALOG.get(ticker)
    warnings: list[str] = []

    if len(frame) < 30:
        raise MarketDataError(f"عدد الشموع غير كافٍ للتحليل ({len(frame)} شمعة)")
    if len(frame) < 210:
        warnings.append("البيانات أقل من 210 شمعة — مؤشرات المدى الطويل (EMA200) قد تكون غير متاحة")

    close, high, low, volume = frame["Close"], frame["High"], frame["Low"], frame["Volume"]
    price = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])

    macd_line, macd_signal, macd_hist = ta.macd(close)
    bb_up, bb_mid, bb_low = ta.bollinger(close)
    stoch_k, stoch_d = ta.stochastic(high, low, close)
    adx_line, plus_di, minus_di = ta.adx(high, low, close)
    atr_series = ta.atr(high, low, close)

    atr_v = _safe(atr_series.iloc[-1])
    bandwidth = (bb_up - bb_low) / bb_mid.replace(0, float("nan"))
    bw_now = _safe(bandwidth.iloc[-1])
    bw_hist = bandwidth.dropna().tail(120)
    squeeze = bool(bw_now is not None and len(bw_hist) > 20 and bw_now <= bw_hist.quantile(0.15))

    avg_vol = _safe(volume.tail(20).mean())
    last_vol = _safe(volume.iloc[-1])

    metrics = {
        "السعر": price,
        "تغير_الجلسة_%": round((price / prev_close - 1) * 100, 2) if prev_close else None,
        "EMA20": _safe(ta.ema(close, 20).iloc[-1]),
        "EMA50": _safe(ta.ema(close, 50).iloc[-1]),
        "EMA200": _safe(ta.ema(close, 200).iloc[-1]),
        "RSI": _safe(ta.rsi(close).iloc[-1]),
        "MACD": _safe(macd_line.iloc[-1]),
        "MACD_إشارة": _safe(macd_signal.iloc[-1]),
        "MACD_هيستوغرام": _safe(macd_hist.iloc[-1]),
        "بولنجر_علوي": _safe(bb_up.iloc[-1]),
        "بولنجر_وسط": _safe(bb_mid.iloc[-1]),
        "بولنجر_سفلي": _safe(bb_low.iloc[-1]),
        "انضغاط_بولنجر": squeeze,
        "ستوكاستيك_K": _safe(stoch_k.iloc[-1]),
        "ستوكاستيك_D": _safe(stoch_d.iloc[-1]),
        "ADX": _safe(adx_line.iloc[-1]),
        "+DI": _safe(plus_di.iloc[-1]),
        "-DI": _safe(minus_di.iloc[-1]),
        "ATR": atr_v,
        "ATR_%": round(atr_v / price * 100, 2) if atr_v and price else None,
        "نسبة_الحجم_للمتوسط": round(last_vol / avg_vol, 2) if avg_vol and last_vol else None,
        "أعلى_52": _safe(high.tail(252).max()),
        "أدنى_52": _safe(low.tail(252).min()),
    }
    metrics = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in metrics.items()}

    supports, resistances = ta.swing_levels(high, low, lookback=min(len(frame), 120))
    last = frame.iloc[-1]
    pivots = ta.pivot_levels(float(last["High"]), float(last["Low"]), float(last["Close"]))
    swing_hi = float(high.tail(120).max())
    swing_lo = float(low.tail(120).min())

    levels = {
        "دعوم": [s for s in supports if s < price][-3:],
        "مقاومات": [r for r in resistances if r > price][:3],
        "نقاط_الارتكاز": {k: round(v, 4) for k, v in pivots.items()},
        "فيبوناتشي": {k: round(v, 4) for k, v in ta.fibonacci_retracement(swing_hi, swing_lo).items()},
    }

    signals = _build_signals(frame, metrics)
    score = _score(signals)

    return Analysis(
        symbol=ticker,
        name_ar=info.ar if info else ticker,
        interval=interval,
        price=price,
        currency=info.currency if info else "USD",
        score=score,
        bias=_bias_label(score),
        signals=signals,
        metrics=metrics,
        levels=levels,
        setup=_trade_setup(price, atr_v, score, levels),
        warnings=warnings,
    )


def analyze(symbol: str, period: str = "1y", interval: str = "1d") -> Analysis:
    """يجلب البيانات ثم يحللها."""
    frame = get_history(symbol, period=period, interval=interval)
    return analyze_frame(symbol, frame, interval=interval)


def compare(symbols: list[str], period: str = "1y") -> dict:
    """يقارن عدة أصول بدرجة القوة — مفيد لاختيار الأفضل ضمن قطاع."""
    rows = []
    for symbol in symbols:
        try:
            result = analyze(symbol, period=period)
            rows.append({
                "الرمز": result.symbol,
                "الاسم": result.name_ar,
                "السعر": round(result.price, 4),
                "درجة_القوة": result.score,
                "الانحياز": result.bias,
                "RSI": result.metrics.get("RSI"),
                "تغير_الجلسة_%": result.metrics.get("تغير_الجلسة_%"),
            })
        except Exception as exc:
            rows.append({"الرمز": to_ticker(symbol), "خطأ": str(exc)})

    rows.sort(key=lambda r: r.get("درجة_القوة", -1), reverse=True)
    return {"المقارنة": rows, "الأقوى": rows[0]["الرمز"] if rows else None}
