"""خريطة الرموز: أسهم إماراتية، فوركس، مؤشرات، سلع، عملات رقمية.

الهدف أن يكتب المستخدم "إعمار" أو "الذهب" أو "اليورو دولار" فنحوّلها إلى رمز
تفهمه مصادر البيانات (Yahoo Finance).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SymbolInfo:
    ticker: str                       # الرمز المستخدم في جلب البيانات
    ar: str                           # الاسم بالعربي
    en: str                           # الاسم بالإنجليزي
    market: str                       # ADX | DFM | FX | INDEX | COMMODITY | CRYPTO | US
    currency: str = "USD"
    aliases: tuple[str, ...] = field(default_factory=tuple)
    fallbacks: tuple[str, ...] = field(default_factory=tuple)  # رموز بديلة لو فشل الأساسي


# ---------------------------------------------------------- سوق أبوظبي (ADX)
# ملاحظة: ياهو يستخدم اللاحقة .AD لأبوظبي و .DU لدبي، ونضيف .AE كبديل احتياطي.
_ADX = [
    ("FAB", "بنك أبوظبي الأول", "First Abu Dhabi Bank", ("fab", "ابوظبي الاول", "أبوظبي الأول")),
    ("ADCB", "بنك أبوظبي التجاري", "Abu Dhabi Commercial Bank", ("adcb", "ابوظبي التجاري")),
    ("ADIB", "مصرف أبوظبي الإسلامي", "Abu Dhabi Islamic Bank", ("adib", "ابوظبي الاسلامي")),
    ("EAND", "اتصالات (e&)", "e& (Etisalat)", ("etisalat", "اتصالات", "اي اند", "e&")),
    ("IHC", "القابضة (IHC)", "International Holding Company", ("ihc", "القابضة", "اي اتش سي")),
    ("ALDAR", "الدار العقارية", "Aldar Properties", ("aldar", "الدار")),
    ("ADNOCDRILL", "أدنوك للحفر", "ADNOC Drilling", ("adnoc drilling", "ادنوك للحفر", "الحفر")),
    ("ADNOCGAS", "أدنوك للغاز", "ADNOC Gas", ("adnoc gas", "ادنوك للغاز", "الغاز")),
    ("ADNOCDIST", "أدنوك للتوزيع", "ADNOC Distribution", ("adnoc distribution", "ادنوك للتوزيع")),
    ("ADPORTS", "موانئ أبوظبي", "AD Ports Group", ("ad ports", "موانئ ابوظبي", "الموانئ")),
    ("TAQA", "طاقة", "TAQA", ("taqa", "طاقة", "ابوظبي الوطنية للطاقة")),
    ("BOROUGE", "بروج", "Borouge", ("borouge", "بروج")),
    ("ALPHADHABI", "ألفا ظبي", "Alpha Dhabi Holding", ("alpha dhabi", "الفا ظبي")),
    ("MULTIPLY", "مالتيبلاي", "Multiply Group", ("multiply", "مالتيبلاي")),
    ("PRESIGHT", "بريسايت", "Presight AI", ("presight", "بريسايت")),
    ("SPACE42", "سبيس42", "Space42", ("space42", "سبيس 42", "ياه سات", "yahsat")),
    ("PUREHEALTH", "بيور هيلث", "PureHealth", ("purehealth", "بيور هيلث")),
    ("BURJEEL", "برجيل", "Burjeel Holdings", ("burjeel", "برجيل")),
    ("AGTHIA", "أغذية", "Agthia Group", ("agthia", "اغذية")),
    ("EMSTEEL", "إعمار ستيل", "Emsteel", ("emsteel", "ام ستيل", "الحديد")),
    ("FERTIGLB", "فيرتيجلوب", "Fertiglobe", ("fertiglobe", "فيرتيجلوب")),
    ("NMDC", "الشركة الوطنية للاستثمارات البحرية", "NMDC Group", ("nmdc",)),
    ("AMERICANA", "أمريكانا", "Americana Restaurants", ("americana", "امريكانا")),
    ("ADNH", "الوطنية للفنادق", "Abu Dhabi National Hotels", ("adnh", "الوطنية للفنادق")),
    ("DANA", "دانة غاز", "Dana Gas", ("dana gas", "دانة غاز")),
    ("WAHA", "الواحة كابيتال", "Waha Capital", ("waha", "الواحة")),
]

# ------------------------------------------------------------ سوق دبي (DFM)
_DFM = [
    ("EMAAR", "إعمار العقارية", "Emaar Properties", ("emaar", "اعمار", "إعمار")),
    ("EMAARDEV", "إعمار للتطوير", "Emaar Development", ("emaar development", "اعمار للتطوير")),
    ("DIB", "بنك دبي الإسلامي", "Dubai Islamic Bank", ("dib", "دبي الاسلامي", "دبي الإسلامي")),
    ("EMIRATESNBD", "بنك الإمارات دبي الوطني", "Emirates NBD", ("enbd", "الامارات دبي الوطني")),
    ("DEWA", "ديوا (كهرباء ومياه دبي)", "DEWA", ("dewa", "ديوا", "كهرباء دبي")),
    ("SALIK", "سالك", "Salik", ("salik", "سالك")),
    ("PARKIN", "باركن", "Parkin", ("parkin", "باركن", "مواقف")),
    ("TECOM", "تيكوم", "TECOM Group", ("tecom", "تيكوم")),
    ("EMPOWER", "إمباور", "Empower", ("empower", "امباور", "إمباور")),
    ("DU", "دو (الإمارات للاتصالات المتكاملة)", "du / EITC", ("du", "دو")),
    ("TALABAT", "طلبات", "Talabat Holding", ("talabat", "طلبات")),
    ("SPINNEYS", "سبينس", "Spinneys", ("spinneys", "سبينس")),
    ("DTC", "تاكسي دبي", "Dubai Taxi Company", ("dubai taxi", "تاكسي دبي", "دي تي سي")),
    ("AIRARABIA", "العربية للطيران", "Air Arabia", ("air arabia", "العربية للطيران")),
    ("ARMX", "أرامكس", "Aramex", ("aramex", "ارامكس")),
    ("CBD", "بنك دبي التجاري", "Commercial Bank of Dubai", ("cbd", "دبي التجاري")),
    ("MASQ", "بنك المشرق", "Mashreqbank", ("mashreq", "المشرق")),
    ("DFM", "سوق دبي المالي", "Dubai Financial Market", ("dfm", "سوق دبي المالي")),
    ("UPP", "الاتحاد العقارية", "Union Properties", ("union properties", "الاتحاد العقارية")),
    ("GFH", "مجموعة جي إف إتش", "GFH Financial Group", ("gfh", "جي اف اتش")),
    ("SHUAA", "شعاع كابيتال", "SHUAA Capital", ("shuaa", "شعاع")),
    ("AMLAK", "أملاك للتمويل", "Amlak Finance", ("amlak", "املاك")),
]

# -------------------------------------------------------------------- الفوركس
_FX = [
    ("EURUSD=X", "يورو / دولار", "EUR/USD", ("eurusd", "eur/usd", "يورو دولار", "اليورو")),
    ("GBPUSD=X", "جنيه / دولار", "GBP/USD", ("gbpusd", "gbp/usd", "باوند", "الجنيه")),
    ("USDJPY=X", "دولار / ين", "USD/JPY", ("usdjpy", "usd/jpy", "ين", "الين")),
    ("USDCHF=X", "دولار / فرنك", "USD/CHF", ("usdchf", "فرنك")),
    ("AUDUSD=X", "دولار أسترالي / دولار", "AUD/USD", ("audusd", "استرالي")),
    ("NZDUSD=X", "دولار نيوزلندي / دولار", "NZD/USD", ("nzdusd", "نيوزلندي")),
    ("USDCAD=X", "دولار / دولار كندي", "USD/CAD", ("usdcad", "كندي")),
    ("EURJPY=X", "يورو / ين", "EUR/JPY", ("eurjpy",)),
    ("GBPJPY=X", "جنيه / ين", "GBP/JPY", ("gbpjpy",)),
    ("EURGBP=X", "يورو / جنيه", "EUR/GBP", ("eurgbp",)),
    ("USDTRY=X", "دولار / ليرة تركية", "USD/TRY", ("usdtry", "ليرة تركية")),
    ("USDCNY=X", "دولار / يوان", "USD/CNY", ("usdcny", "يوان")),
    ("USDEGP=X", "دولار / جنيه مصري", "USD/EGP", ("usdegp", "جنيه مصري")),
    ("USDSAR=X", "دولار / ريال سعودي", "USD/SAR", ("usdsar", "ريال سعودي")),
    ("USDAED=X", "دولار / درهم", "USD/AED", ("usdaed", "درهم", "الدرهم")),
    ("DX-Y.NYB", "مؤشر الدولار", "US Dollar Index (DXY)", ("dxy", "مؤشر الدولار", "الدولار")),
]

# ------------------------------------------------------------------- المؤشرات
_INDICES = [
    ("^GSPC", "ستاندرد آند بورز 500", "S&P 500", ("sp500", "s&p", "اس اند بي", "سبي")),
    ("^IXIC", "ناسداك المجمع", "Nasdaq Composite", ("nasdaq", "ناسداك")),
    ("^NDX", "ناسداك 100", "Nasdaq 100", ("ndx", "ناسداك 100")),
    ("^DJI", "داو جونز", "Dow Jones", ("dow", "داو", "داو جونز")),
    ("^RUT", "راسل 2000", "Russell 2000", ("russell", "راسل")),
    ("^VIX", "مؤشر الخوف", "VIX Volatility Index", ("vix", "الخوف", "التقلب")),
    ("^FTSE", "فوتسي 100", "FTSE 100", ("ftse", "فوتسي")),
    ("^GDAXI", "داكس الألماني", "DAX", ("dax", "داكس")),
    ("^FCHI", "كاك الفرنسي", "CAC 40", ("cac", "كاك")),
    ("^N225", "نيكاي الياباني", "Nikkei 225", ("nikkei", "نيكاي")),
    ("^HSI", "هانج سنج", "Hang Seng", ("hangseng", "هانج سنج")),
    ("^TNX", "عائد سندات 10 سنوات", "US 10Y Treasury Yield", ("10y", "العشر سنوات", "السندات")),
]

# --------------------------------------------------------------------- السلع
_COMMODITIES = [
    ("GC=F", "الذهب", "Gold Futures", ("gold", "ذهب", "الذهب", "xauusd", "xau")),
    ("SI=F", "الفضة", "Silver Futures", ("silver", "فضة", "الفضة", "xagusd")),
    ("CL=F", "النفط الأمريكي", "WTI Crude Oil", ("wti", "نفط", "النفط", "الخام")),
    ("BZ=F", "خام برنت", "Brent Crude Oil", ("brent", "برنت")),
    ("NG=F", "الغاز الطبيعي", "Natural Gas", ("natgas", "الغاز الطبيعي")),
    ("HG=F", "النحاس", "Copper", ("copper", "النحاس")),
    ("PL=F", "البلاتين", "Platinum", ("platinum", "البلاتين")),
]

# ------------------------------------------------------------ العملات الرقمية
_CRYPTO = [
    ("BTC-USD", "بيتكوين", "Bitcoin", ("btc", "bitcoin", "بتكوين", "بيتكوين")),
    ("ETH-USD", "إيثيريوم", "Ethereum", ("eth", "ethereum", "ايثيريوم")),
    ("SOL-USD", "سولانا", "Solana", ("sol", "solana", "سولانا")),
    ("XRP-USD", "ريبل", "XRP", ("xrp", "ripple", "ريبل")),
    ("BNB-USD", "بينانس كوين", "BNB", ("bnb", "بينانس")),
]

# --------------------------------------------- أسهم عالمية شائعة (اختصارات)
_US = [
    ("AAPL", "آبل", "Apple", ("apple", "ابل", "آبل")),
    ("MSFT", "مايكروسوفت", "Microsoft", ("microsoft", "مايكروسوفت")),
    ("NVDA", "إنفيديا", "NVIDIA", ("nvidia", "انفيديا", "إنفيديا")),
    ("GOOGL", "جوجل", "Alphabet", ("google", "جوجل", "الفابت")),
    ("AMZN", "أمازون", "Amazon", ("amazon", "امازون")),
    ("META", "ميتا", "Meta Platforms", ("facebook", "ميتا", "فيسبوك")),
    ("TSLA", "تسلا", "Tesla", ("tesla", "تسلا")),
    ("BRK-B", "بيركشاير هاثاواي", "Berkshire Hathaway", ("berkshire", "بيركشاير")),
    ("JPM", "جي بي مورغان", "JPMorgan Chase", ("jpmorgan", "جي بي مورغان")),
    ("XOM", "إكسون موبيل", "Exxon Mobil", ("exxon", "اكسون")),
]


def _build() -> dict[str, SymbolInfo]:
    catalog: dict[str, SymbolInfo] = {}

    for code, ar, en, aliases in _ADX:
        catalog[f"{code}.AD"] = SymbolInfo(
            f"{code}.AD", ar, en, "ADX", "AED", aliases + (code.lower(),), (f"{code}.AE",)
        )
    for code, ar, en, aliases in _DFM:
        catalog[f"{code}.DU"] = SymbolInfo(
            f"{code}.DU", ar, en, "DFM", "AED", aliases + (code.lower(),), (f"{code}.AE",)
        )
    for ticker, ar, en, aliases in _FX:
        catalog[ticker] = SymbolInfo(ticker, ar, en, "FX", "USD", aliases)
    for ticker, ar, en, aliases in _INDICES:
        catalog[ticker] = SymbolInfo(ticker, ar, en, "INDEX", "USD", aliases)
    for ticker, ar, en, aliases in _COMMODITIES:
        catalog[ticker] = SymbolInfo(ticker, ar, en, "COMMODITY", "USD", aliases)
    for ticker, ar, en, aliases in _CRYPTO:
        catalog[ticker] = SymbolInfo(ticker, ar, en, "CRYPTO", "USD", aliases)
    for ticker, ar, en, aliases in _US:
        catalog[ticker] = SymbolInfo(ticker, ar, en, "US", "USD", aliases + (ticker.lower(),))

    return catalog


CATALOG: dict[str, SymbolInfo] = _build()

# فهرس البحث: كل اسم مستعار -> الرمز
_ALIAS_INDEX: dict[str, str] = {}
for _ticker, _info in CATALOG.items():
    _ALIAS_INDEX[_ticker.lower()] = _ticker
    _ALIAS_INDEX[_info.ar] = _ticker
    _ALIAS_INDEX[_info.en.lower()] = _ticker
    for _alias in _info.aliases:
        _ALIAS_INDEX.setdefault(_alias.lower(), _ticker)

# مجموعات جاهزة للماسح
GROUPS = {
    "uae": [t for t, i in CATALOG.items() if i.market in ("ADX", "DFM")],
    "adx": [t for t, i in CATALOG.items() if i.market == "ADX"],
    "dfm": [t for t, i in CATALOG.items() if i.market == "DFM"],
    "forex": [t for t, i in CATALOG.items() if i.market == "FX"],
    "indices": [t for t, i in CATALOG.items() if i.market == "INDEX"],
    "commodities": [t for t, i in CATALOG.items() if i.market == "COMMODITY"],
    "crypto": [t for t, i in CATALOG.items() if i.market == "CRYPTO"],
    "us": [t for t, i in CATALOG.items() if i.market == "US"],
}

_ARABIC_DIACRITICS = re.compile(r"[ً-ْـ]")


def normalize_ar(text: str) -> str:
    """تطبيع النص العربي: حذف التشكيل وتوحيد الألف والهاء/التاء المربوطة."""
    text = _ARABIC_DIACRITICS.sub("", text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    return text.strip().lower()


_NORM_INDEX: dict[str, str] = {normalize_ar(k): v for k, v in _ALIAS_INDEX.items()}


def resolve(query: str) -> SymbolInfo | None:
    """يحوّل نصاً حراً (عربي أو إنجليزي) إلى رمز معروف، أو None."""
    if not query:
        return None
    raw = query.strip()

    # مطابقة مباشرة على الرمز كما هو (يشمل رموزاً غير موجودة في القائمة)
    if raw.upper() in CATALOG:
        return CATALOG[raw.upper()]

    key = normalize_ar(raw)
    ticker = _NORM_INDEX.get(key)
    if ticker:
        return CATALOG[ticker]

    # مطابقة جزئية: "سهم إعمار" أو "سعر الذهب اليوم"
    matches = [t for alias, t in _NORM_INDEX.items() if len(alias) >= 3 and alias in key]
    if len(set(matches)) == 1:
        return CATALOG[matches[0]]
    if matches:
        # نرجّح أطول اسم مستعار مطابق (الأكثر تحديداً)
        best = max(
            ((alias, t) for alias, t in _NORM_INDEX.items() if len(alias) >= 3 and alias in key),
            key=lambda pair: len(pair[0]),
        )
        return CATALOG[best[1]]

    return None


def to_ticker(query: str) -> str:
    """يعيد رمزاً صالحاً للاستخدام — إن لم يُعرف الاسم نعيده كما هو بحروف كبيرة."""
    info = resolve(query)
    return info.ticker if info else query.strip().upper()


def describe(ticker: str) -> str:
    """وصف عربي قصير للرمز."""
    info = CATALOG.get(ticker.upper())
    return f"{info.ar} ({ticker})" if info else ticker


def search(query: str, limit: int = 8) -> list[SymbolInfo]:
    """بحث نصي يعيد عدة نتائج محتملة."""
    key = normalize_ar(query)
    if not key:
        return []
    hits: list[tuple[int, SymbolInfo]] = []
    seen: set[str] = set()
    for alias, ticker in _NORM_INDEX.items():
        if ticker in seen:
            continue
        if key in alias or alias in key:
            seen.add(ticker)
            hits.append((0 if alias.startswith(key) else 1, CATALOG[ticker]))
    hits.sort(key=lambda pair: pair[0])
    return [info for _, info in hits[:limit]]
