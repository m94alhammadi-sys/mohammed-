"""إعداد بيئة الاختبار — يجب أن يسبق أي استيراد من app."""

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="advisor_tests_")
os.environ.setdefault("DB_PATH", os.path.join(_TMP, "test.db"))
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-not-used")
os.environ.setdefault("META_ACCESS_TOKEN", "test-token")
os.environ.setdefault("META_PHONE_NUMBER_ID", "1234567890")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify")
os.environ.setdefault("ALLOWED_NUMBERS", "971500000000")
os.environ.setdefault("OWNER_NUMBER", "971500000000")
os.environ.setdefault("TZ", "Asia/Dubai")

import numpy as np
import pandas as pd
import pytest


@pytest.fixture(scope="session")
def phone() -> str:
    return "971500000000"


def make_candles(n: int = 400, drift: float = 0.0, noise: float = 0.006, seed: int = 0) -> pd.DataFrame:
    """شموع صناعية لاختبار التحليل بدون إنترنت.

    نستخدم نمواً مركّباً (هندسياً) لأن الأسعار الحقيقية تتحرك بنسب مئوية لا
    بمقادير ثابتة — وهذا يمنع ظهور أسعار سالبة في الاتجاهات الهابطة الطويلة.
    ``drift`` هو العائد اليومي المتوقع (0.004 ≈ +0.4% يومياً).
    """
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-01", periods=n, freq="B")
    returns = rng.normal(drift, noise, n)
    close = pd.Series(100 * np.exp(np.cumsum(returns)), index=index)
    return pd.DataFrame({
        "Open": close.shift(1).fillna(close.iloc[0]),
        "High": close * 1.006,
        "Low": close * 0.994,
        "Close": close,
        "Volume": pd.Series(rng.integers(500_000, 2_000_000, n).astype(float), index=index),
    })


@pytest.fixture
def uptrend() -> pd.DataFrame:
    return make_candles(drift=0.006, noise=0.004, seed=0)   # درجة 73.6 — فوق عتبة التنبيه


@pytest.fixture
def downtrend() -> pd.DataFrame:
    return make_candles(drift=-0.005, noise=0.004, seed=10)  # درجة 26.4 — تحت عتبة التنبيه


@pytest.fixture
def sideways() -> pd.DataFrame:
    return make_candles(drift=0.0, noise=0.012, seed=9)      # درجة 50.0 — محايد تماماً


@pytest.fixture
def clean_db(phone):
    """قاعدة بيانات نظيفة لكل اختبار."""
    from app import db

    db.init_db()
    with db.tx() as conn:
        for table in ("users", "messages", "watchlist", "alerts", "price_alerts", "reminders", "memory", "kv"):
            conn.execute(f"DELETE FROM {table}")
    db.ensure_user(phone, "محمد")
    return db


@pytest.fixture
def plain_phone(clean_db):
    """المشترك الوحيد في القاعدة، وليس صاحب الحساب.

    صاحب الحساب تُضاف له الرموز الأساسية تلقائياً في المسح، فنعزله هنا حتى
    تقيس الاختبارات رمزاً واحداً بالضبط.
    """
    from app import db

    number = "971502223333"
    with db.tx() as conn:
        conn.execute("DELETE FROM users")
    db.ensure_user(number, "مشترك")
    return number
