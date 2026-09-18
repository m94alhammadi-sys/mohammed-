"""تعريف أدوات الوكيل وتنفيذها.

كل أداة تُرجع نصاً (JSON بالعربية) يعود للنموذج كـ tool_result.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .. import db
from ..config import settings
from ..market import calendar_econ, news
from ..market.analysis import analyze, compare
from ..market.data import MarketDataError, correlation, get_quote, get_quotes, performance
from ..market.symbols import CATALOG, GROUPS, describe, search, to_ticker

log = logging.getLogger(__name__)


def _json(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _err(message: str) -> str:
    return _json({"خطأ": message})


# ==========================================================================
#                          تعريفات الأدوات (schemas)
# ==========================================================================

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "get_price",
        "description": (
            "يجلب السعر الحالي (أو آخر إغلاق) لرمز أو عدة رموز، مع التغير اليومي وحجم "
            "التداول والمدى السنوي. يقبل أسماء عربية مثل «إعمار» أو «الذهب» أو رموزاً مثل "
            "AAPL أو EURUSD=X. استخدمه لأي سؤال عن سعر."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "قائمة الرموز أو الأسماء المطلوبة (حتى 15 رمزاً).",
                }
            },
            "required": ["symbols"],
        },
    },
    {
        "name": "technical_analysis",
        "description": (
            "تحليل فني كامل لرمز: الاتجاه، RSI، ماكد، بولنجر، ADX، ATR، الدعوم والمقاومات، "
            "فيبوناتشي، درجة قوة الإشارة (0-100)، وسيناريو تداول مقترح مع وقف خسارة وأهداف. "
            "استخدمه لأي سؤال عن التحليل أو «وش رايك في السهم»."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "الرمز أو الاسم."},
                "timeframe": {
                    "type": "string",
                    "enum": ["يومي", "أسبوعي", "ساعة", "4ساعات", "15دقيقة"],
                    "description": "الإطار الزمني للتحليل. الافتراضي: يومي.",
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "compare_symbols",
        "description": "يقارن عدة رموز بدرجة القوة الفنية ويرتّبها من الأقوى للأضعف.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["symbols"],
        },
    },
    {
        "name": "performance_returns",
        "description": "عوائد رمز عبر فترات (يوم، أسبوع، شهر، 3 أشهر، 6 أشهر، سنة، منذ بداية العام).",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "correlation_matrix",
        "description": (
            "مصفوفة الارتباط بين عدة أصول — لمعرفة هل المحفظة منوّعة فعلاً أم أن كل "
            "مراكزها تتحرك معاً."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}},
                "period": {"type": "string", "enum": ["3mo", "6mo", "1y", "2y"]},
            },
            "required": ["symbols"],
        },
    },
    {
        "name": "market_movers",
        "description": (
            "أكبر الرابحين والخاسرين ضمن مجموعة سوقية. المجموعات المتاحة: uae (الإمارات)، "
            "adx (أبوظبي)، dfm (دبي)، forex، indices (المؤشرات)، commodities (السلع)، "
            "crypto (العملات الرقمية)، us (أسهم أمريكية)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "group": {
                    "type": "string",
                    "enum": ["uae", "adx", "dfm", "forex", "indices", "commodities", "crypto", "us"],
                },
                "limit": {"type": "integer", "description": "عدد الأسماء في كل جهة (افتراضي 5)."},
            },
            "required": ["group"],
        },
    },
    {
        "name": "search_symbols",
        "description": "يبحث عن الرمز الصحيح لاسم شركة أو أصل عندما لا تكون متأكداً منه.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "get_news",
        "description": (
            "أخبار مالية من مصادر عربية وعالمية. مرّر symbol لأخبار سهم معيّن، أو query "
            "لبحث حر، أو region (global / uae / gulf) لأهم العناوين."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "query": {"type": "string"},
                "region": {"type": "string", "enum": ["global", "uae", "gulf"]},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "economic_calendar",
        "description": (
            "المفكرة الاقتصادية: قرارات الفائدة، التضخم، الوظائف، الناتج المحلي. "
            "scope: today (اليوم) / upcoming (القادم) / recent (صدر للتو مع المفاجأة "
            "مقابل التوقعات)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["today", "upcoming", "recent"]},
                "days_ahead": {"type": "integer", "description": "للنطاق upcoming، افتراضي 7."},
                "only_high_impact": {"type": "boolean"},
            },
            "required": ["scope"],
        },
    },
    {
        "name": "position_size",
        "description": (
            "حاسبة إدارة المخاطر: تحسب حجم المركز المناسب بناءً على رأس المال ونسبة "
            "المخاطرة وسعر الدخول ووقف الخسارة."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "capital": {"type": "number", "description": "رأس المال الإجمالي."},
                "risk_percent": {"type": "number", "description": "نسبة المخاطرة من رأس المال (مثلاً 1 أو 2)."},
                "entry": {"type": "number"},
                "stop_loss": {"type": "number"},
                "target": {"type": "number", "description": "اختياري — لحساب المخاطرة/العائد."},
            },
            "required": ["capital", "risk_percent", "entry", "stop_loss"],
        },
    },
    {
        "name": "manage_watchlist",
        "description": (
            "إدارة قائمة متابعة المستخدم — الرموز التي يفحصها الماسح الآلي كل ربع ساعة "
            "بحثاً عن فرص. action: add / remove / show."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["add", "remove", "show"]},
                "symbols": {"type": "array", "items": {"type": "string"}},
                "note": {"type": "string", "description": "ملاحظة اختيارية (مثل سعر الشراء)."},
            },
            "required": ["action"],
        },
    },
    {
        "name": "manage_price_alert",
        "description": (
            "تنبيه سعري: أخبرني إذا وصل الرمز لسعر معيّن. action: set / list / cancel."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["set", "list", "cancel"]},
                "symbol": {"type": "string"},
                "direction": {
                    "type": "string",
                    "enum": ["above", "below"],
                    "description": "above = عند الصعود فوق السعر، below = عند النزول تحته.",
                },
                "price": {"type": "number"},
                "note": {"type": "string"},
                "alert_id": {"type": "integer", "description": "للإلغاء."},
            },
            "required": ["action"],
        },
    },
    {
        "name": "manage_reminder",
        "description": (
            "تذكير شخصي في وقت محدد أو يومياً. action: create / list / cancel. "
            "للتذكير لمرة واحدة استخدم at (مثل '2026-09-20 14:30') أو in_minutes. "
            "للتذكير اليومي استخدم daily_time بصيغة HH:MM."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "list", "cancel"]},
                "text": {"type": "string", "description": "نص التذكير."},
                "at": {"type": "string", "description": "وقت محدد بصيغة YYYY-MM-DD HH:MM بتوقيت المستخدم."},
                "in_minutes": {"type": "integer", "description": "بعد كم دقيقة من الآن."},
                "daily_time": {"type": "string", "description": "HH:MM لتذكير يومي متكرر."},
                "reminder_id": {"type": "integer", "description": "للإلغاء."},
            },
            "required": ["action"],
        },
    },
    {
        "name": "remember_fact",
        "description": (
            "احفظ معلومة دائمة عن المستخدم تفيدك لاحقاً: أسلوبه في التداول، حجم محفظته، "
            "مراكزه المفتوحة، تفضيلاته، القطاعات التي يتجنبها. تُستدعى تلقائياً في كل محادثة."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "عنوان قصير للمعلومة."},
                "value": {"type": "string", "description": "المعلومة نفسها."},
            },
            "required": ["key", "value"],
        },
    },
]


def server_tools() -> list[dict]:
    """أدوات الخادم من Anthropic: البحث والجلب من الإنترنت."""
    return [
        {
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": settings.web_search_max_uses,
        },
        {
            "type": "web_fetch_20260209",
            "name": "web_fetch",
            "max_uses": max(settings.web_search_max_uses // 2, 3),
        },
    ]


# ==========================================================================
#                               التنفيذ
# ==========================================================================

_TIMEFRAMES = {
    "يومي": ("1y", "1d"),
    "أسبوعي": ("5y", "1wk"),
    "ساعة": ("60d", "1h"),
    "4ساعات": ("180d", "1h"),
    "15دقيقة": ("30d", "15m"),
}


def _tool_get_price(args: dict, phone: str) -> str:
    symbols = args.get("symbols") or []
    if not symbols:
        return _err("لم تُحدَّد أي رموز")
    return _json({"الأسعار": get_quotes(symbols[:15])})


def _tool_technical_analysis(args: dict, phone: str) -> str:
    symbol = args.get("symbol", "")
    period, interval = _TIMEFRAMES.get(args.get("timeframe", "يومي"), _TIMEFRAMES["يومي"])
    try:
        result = analyze(symbol, period=period, interval=interval)
    except MarketDataError as exc:
        return _err(str(exc))
    except Exception as exc:
        log.exception("فشل التحليل الفني لـ %s", symbol)
        return _err(f"تعذّر تحليل {describe(to_ticker(symbol))}: {exc}")
    return _json(result.to_dict())


def _tool_compare(args: dict, phone: str) -> str:
    symbols = args.get("symbols") or []
    if len(symbols) < 2:
        return _err("أحتاج رمزين على الأقل للمقارنة")
    return _json(compare(symbols[:8]))


def _tool_performance(args: dict, phone: str) -> str:
    try:
        return _json(performance(args.get("symbol", "")))
    except Exception as exc:
        return _err(str(exc))


def _tool_correlation(args: dict, phone: str) -> str:
    return _json(correlation(args.get("symbols") or [], args.get("period", "6mo")))


def _tool_market_movers(args: dict, phone: str) -> str:
    group = args.get("group", "uae")
    limit = int(args.get("limit") or 5)
    tickers = GROUPS.get(group, [])
    if not tickers:
        return _err(f"مجموعة غير معروفة: {group}")

    quotes = [q for q in get_quotes(tickers[:30]) if "خطأ" not in q]
    if not quotes:
        return _err(f"تعذّر جلب بيانات مجموعة {group}")

    quotes.sort(key=lambda q: q.get("التغير_نسبة_مئوية", 0), reverse=True)
    return _json({
        "المجموعة": group,
        "عدد_الرموز_المفحوصة": len(quotes),
        "أكبر_الرابحين": quotes[:limit],
        "أكبر_الخاسرين": quotes[-limit:][::-1],
    })


def _tool_search_symbols(args: dict, phone: str) -> str:
    results = search(args.get("query", ""))
    return _json({
        "النتائج": [
            {"الرمز": r.ticker, "الاسم_العربي": r.ar, "الاسم_الإنجليزي": r.en, "السوق": r.market}
            for r in results
        ]
        or "لم أجد تطابقاً — جرّب الرمز مباشرة أو ابحث في الإنترنت"
    })


def _tool_get_news(args: dict, phone: str) -> str:
    limit = int(args.get("limit") or 8)
    if args.get("symbol"):
        return _json({"أخبار": news.ticker_news(args["symbol"], limit)})
    if args.get("query"):
        return _json({"أخبار": news.search_news(args["query"], limit)})
    return _json({"أخبار": news.market_headlines(args.get("region", "global"), limit)})


def _tool_economic_calendar(args: dict, phone: str) -> str:
    scope = args.get("scope", "upcoming")
    high_only = args.get("only_high_impact", True)
    if scope == "today":
        return _json({"أحداث_اليوم": calendar_econ.today_events(only_high_impact=high_only)})
    if scope == "recent":
        return _json({"بيانات_صدرت": calendar_econ.recent_releases()})
    days = int(args.get("days_ahead") or 7)
    return _json({"أحداث_قادمة": calendar_econ.upcoming_events(days, only_high_impact=high_only)})


def _tool_position_size(args: dict, phone: str) -> str:
    try:
        capital = float(args["capital"])
        risk_pct = float(args["risk_percent"])
        entry = float(args["entry"])
        stop = float(args["stop_loss"])
    except (KeyError, TypeError, ValueError):
        return _err("أحتاج: رأس المال، نسبة المخاطرة، سعر الدخول، وقف الخسارة")

    risk_per_unit = abs(entry - stop)
    if risk_per_unit == 0:
        return _err("سعر الدخول ووقف الخسارة متطابقان — لا يمكن حساب المخاطرة")
    if capital <= 0 or risk_pct <= 0:
        return _err("رأس المال ونسبة المخاطرة يجب أن يكونا أكبر من صفر")

    risk_amount = capital * risk_pct / 100
    units = risk_amount / risk_per_unit
    position_value = units * entry

    result = {
        "رأس_المال": round(capital, 2),
        "نسبة_المخاطرة_%": risk_pct,
        "المبلغ_المخاطر_به": round(risk_amount, 2),
        "المخاطرة_للوحدة": round(risk_per_unit, 4),
        "عدد_الوحدات": round(units, 4),
        "قيمة_المركز": round(position_value, 2),
        "نسبة_المركز_من_رأس_المال_%": round(position_value / capital * 100, 1),
    }
    if result["نسبة_المركز_من_رأس_المال_%"] > 100:
        result["تحذير"] = (
            "حجم المركز المطلوب يتجاوز رأس المال — وقف الخسارة قريب جداً من الدخول. "
            "وسّع الوقف أو قلّل نسبة المخاطرة."
        )

    target = args.get("target")
    if target:
        reward = abs(float(target) - entry)
        result["المخاطرة_للعائد"] = round(reward / risk_per_unit, 2)
        result["الربح_المحتمل"] = round(units * reward, 2)
        if result["المخاطرة_للعائد"] < 1.5:
            result["ملاحظة"] = "نسبة المخاطرة للعائد أقل من 1.5 — الصفقة غير مجدية إحصائياً"

    return _json(result)


def _tool_watchlist(args: dict, phone: str) -> str:
    action = args.get("action", "show")
    symbols = args.get("symbols") or []

    if action == "add":
        if not symbols:
            return _err("لم تُحدَّد رموز للإضافة")
        added = []
        for symbol in symbols:
            ticker = to_ticker(symbol)
            info = CATALOG.get(ticker)
            db.add_watch(phone, ticker, info.ar if info else None, args.get("note"))
            added.append(describe(ticker))
        return _json({"تمت_الإضافة": added, "ملاحظة": "الماسح الآلي سيراقبها من الآن"})

    if action == "remove":
        removed = [describe(to_ticker(s)) for s in symbols if db.remove_watch(phone, to_ticker(s))]
        return _json({"تم_الحذف": removed or "لم يُعثر على الرموز في القائمة"})

    rows = db.get_watchlist(phone)
    if not rows:
        return _json({"القائمة": "فارغة"})
    return _json({
        "القائمة": [
            {"الرمز": r["symbol"], "الاسم": r["label"], "ملاحظة": r["notes"]} for r in rows
        ]
    })


def _tool_price_alert(args: dict, phone: str) -> str:
    action = args.get("action", "list")

    if action == "set":
        symbol, direction, price = args.get("symbol"), args.get("direction"), args.get("price")
        if not (symbol and direction and price is not None):
            return _err("أحتاج: الرمز، الاتجاه (above/below)، والسعر")
        ticker = to_ticker(symbol)
        try:
            alert_id = db.add_price_alert(phone, ticker, direction, float(price), args.get("note"))
        except ValueError as exc:
            return _err(str(exc))
        arrow = "فوق" if direction == "above" else "تحت"
        return _json({
            "تم": f"سأنبهك إذا تجاوز {describe(ticker)} {arrow} {price}",
            "رقم_التنبيه": alert_id,
        })

    if action == "cancel":
        alert_id = args.get("alert_id")
        if not alert_id:
            return _err("أحتاج رقم التنبيه")
        return _json({"تم": "أُلغي التنبيه"} if db.cancel_price_alert(phone, int(alert_id))
                     else {"خطأ": "لم أجد تنبيهاً بهذا الرقم"})

    rows = db.active_price_alerts(phone)
    return _json({
        "التنبيهات_النشطة": [
            {
                "رقم": r["id"],
                "الرمز": describe(r["symbol"]),
                "الشرط": ("فوق " if r["direction"] == "above" else "تحت ") + str(r["price"]),
                "ملاحظة": r["note"],
            }
            for r in rows
        ] or "لا توجد تنبيهات نشطة"
    })


def _tool_reminder(args: dict, phone: str) -> str:
    action = args.get("action", "list")
    tz = ZoneInfo(settings.timezone)

    if action == "create":
        text = args.get("text")
        if not text:
            return _err("أحتاج نص التذكير")

        if args.get("daily_time"):
            hhmm = str(args["daily_time"]).strip()
            try:
                hh, mm = hhmm.split(":")
                hhmm = f"{int(hh):02d}:{int(mm):02d}"
            except ValueError:
                return _err("صيغة الوقت اليومي يجب أن تكون HH:MM")
            reminder_id = db.add_reminder(phone, text, repeat_daily=hhmm)
            return _json({"تم": f"سأذكرك يومياً الساعة {hhmm}", "رقم_التذكير": reminder_id})

        if args.get("in_minutes"):
            due = datetime.now(tz) + timedelta(minutes=int(args["in_minutes"]))
        elif args.get("at"):
            raw = str(args["at"]).strip().replace("T", " ")
            try:
                due = datetime.strptime(raw[:16], "%Y-%m-%d %H:%M").replace(tzinfo=tz)
            except ValueError:
                return _err("صيغة الوقت يجب أن تكون YYYY-MM-DD HH:MM")
        else:
            return _err("حدّد at أو in_minutes أو daily_time")

        if due <= datetime.now(tz):
            return _err("الوقت المطلوب في الماضي")
        reminder_id = db.add_reminder(phone, text, due_at=due)
        return _json({
            "تم": f"سأذكرك في {due.strftime('%Y-%m-%d %H:%M')} بتوقيت {settings.timezone}",
            "رقم_التذكير": reminder_id,
        })

    if action == "cancel":
        reminder_id = args.get("reminder_id")
        if not reminder_id:
            return _err("أحتاج رقم التذكير")
        return _json({"تم": "أُلغي التذكير"} if db.cancel_reminder(phone, int(reminder_id))
                     else {"خطأ": "لم أجد تذكيراً بهذا الرقم"})

    rows = db.list_reminders(phone)
    return _json({
        "التذكيرات": [
            {
                "رقم": r["id"],
                "النص": r["text"],
                "الموعد": r["due_at"] or f"يومياً {r['repeat_daily']}",
            }
            for r in rows
        ] or "لا توجد تذكيرات"
    })


def _tool_remember(args: dict, phone: str) -> str:
    key, value = args.get("key"), args.get("value")
    if not (key and value):
        return _err("أحتاج المفتاح والقيمة")
    db.remember(phone, key, value)
    return _json({"تم_الحفظ": {key: value}})


_HANDLERS = {
    "get_price": _tool_get_price,
    "technical_analysis": _tool_technical_analysis,
    "compare_symbols": _tool_compare,
    "performance_returns": _tool_performance,
    "correlation_matrix": _tool_correlation,
    "market_movers": _tool_market_movers,
    "search_symbols": _tool_search_symbols,
    "get_news": _tool_get_news,
    "economic_calendar": _tool_economic_calendar,
    "position_size": _tool_position_size,
    "manage_watchlist": _tool_watchlist,
    "manage_price_alert": _tool_price_alert,
    "manage_reminder": _tool_reminder,
    "remember_fact": _tool_remember,
}


def dispatch(name: str, args: dict, phone: str) -> str:
    """ينفّذ الأداة ويعيد نتيجة نصية. لا يرمي استثناءات — يعيد خطأً مفهوماً."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return _err(f"أداة غير معروفة: {name}")
    try:
        return handler(args or {}, phone)
    except Exception as exc:
        log.exception("فشل تنفيذ الأداة %s", name)
        return _err(f"فشل تنفيذ {name}: {exc}")
