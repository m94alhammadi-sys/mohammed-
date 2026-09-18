"""اختبارات التعرّف على الرموز بالعربي والإنجليزي."""

import pytest

from app.market import symbols as sym


@pytest.mark.parametrize("query,expected", [
    ("إعمار", "EMAAR.DU"),
    ("اعمار", "EMAAR.DU"),          # بدون همزة
    ("emaar", "EMAAR.DU"),
    ("بنك أبوظبي الأول", "FAB.AD"),
    ("FAB", "FAB.AD"),
    ("سالك", "SALIK.DU"),
    ("الذهب", "GC=F"),
    ("gold", "GC=F"),
    ("xauusd", "GC=F"),
    ("النفط", "CL=F"),
    ("برنت", "BZ=F"),
    ("يورو دولار", "EURUSD=X"),
    ("بيتكوين", "BTC-USD"),
    ("ناسداك", "^IXIC"),
    ("tesla", "TSLA"),
    ("اتصالات", "EAND.AD"),
    ("ديوا", "DEWA.DU"),
])
def test_resolve_known_symbols(query, expected):
    result = sym.resolve(query)
    assert result is not None, f"لم يتعرّف على: {query}"
    assert result.ticker == expected


def test_resolve_inside_sentence():
    """يجب أن يلتقط الرمز داخل جملة كاملة."""
    assert sym.resolve("شحال سعر إعمار اليوم").ticker == "EMAAR.DU"
    assert sym.resolve("وش رايك في الذهب").ticker == "GC=F"


def test_unknown_symbol_returns_none():
    assert sym.resolve("زززز غير موجود") is None


def test_to_ticker_passes_through_unknown():
    """رمز غير معروف يمر كما هو — قد يكون صالحاً في ياهو."""
    assert sym.to_ticker("nflx") == "NFLX"


def test_normalize_arabic():
    assert sym.normalize_ar("إعمار") == sym.normalize_ar("اعمار")
    assert sym.normalize_ar("شركة") == sym.normalize_ar("شركه")


def test_uae_symbols_have_correct_suffixes():
    for ticker in sym.GROUPS["adx"]:
        assert ticker.endswith(".AD")
        assert sym.CATALOG[ticker].currency == "AED"
    for ticker in sym.GROUPS["dfm"]:
        assert ticker.endswith(".DU")


def test_uae_symbols_have_ae_fallback():
    """لاحقة .AE احتياطية لأن المصادر تختلف في تسمية الأسواق الإماراتية."""
    info = sym.CATALOG["EMAAR.DU"]
    assert "EMAAR.AE" in info.fallbacks


def test_search_returns_multiple_candidates():
    results = sym.search("ادنوك")
    assert len(results) >= 3
    assert all(r.market == "ADX" for r in results)


def test_describe_formats_arabic_name():
    assert sym.describe("EMAAR.DU") == "إعمار العقارية (EMAAR.DU)"


def test_groups_are_populated():
    assert len(sym.GROUPS["uae"]) >= 40
    assert len(sym.GROUPS["forex"]) >= 10
    for group in sym.GROUPS.values():
        assert all(t in sym.CATALOG for t in group)
