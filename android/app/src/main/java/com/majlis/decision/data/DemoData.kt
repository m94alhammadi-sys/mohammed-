package com.majlis.decision.data

/**
 * بيانات عرض توضيحية — تظهر حين لا يكون خادم «مجلس القرار» متاحاً.
 *
 * موسومة صراحةً في الواجهة بشارة «عرض توضيحي» حتى لا تُقرأ كتحليل
 * حقيقي؛ وهو نفس المبدأ المطبّق في الخادم: لا نعرض رأياً مُختلقاً
 * على أنه تحليل.
 */
object DemoData {

    val agents = listOf(
        Agent(
            id = "breaking_desk", name = "غرفة العاجل", role = "الأحداث الطارئة",
            initials = "عا", accentArgb = 0xFFE74C3C,
            specialty = "كسر إخباري", sources = "3 حية", confidence = 0.62,
            lastReport = "قبل 8 دقائق", status = "نشط",
        ),
        Agent(
            id = "political_analyst", name = "المحلل السياسي", role = "الجيوسياسة",
            initials = "سي", accentArgb = 0xFF8E44AD,
            specialty = "قرارات حكومية", sources = "4 حية", confidence = 0.58,
            lastReport = "قبل 12 دقيقة", status = "نشط", selected = true,
        ),
        Agent(
            id = "economic_analyst", name = "المحلل الاقتصادي", role = "الاقتصاد الكلي",
            initials = "اق", accentArgb = 0xFF2980B9,
            specialty = "فائدة وتضخم", sources = "6 سلاسل", confidence = 0.71,
            lastReport = "قبل 15 دقيقة", status = "نشط",
        ),
        Agent(
            id = "the_trader", name = "التاجر", role = "تدفقات السوق",
            initials = "تج", accentArgb = 0xFFF39C12,
            specialty = "حيتان وسيولة", sources = "8 أدوات", confidence = 0.66,
            lastReport = "قبل 6 دقائق", status = "نشط",
        ),
        Agent(
            id = "abu_aloloum", name = "بوالعلوم", role = "مشاعر التواصل",
            initials = "بع", accentArgb = 0xFF25D366,
            specialty = "زخم ورأي عام", sources = "بانتظار مفاتيح", confidence = 0.41,
            lastReport = "قبل 10 دقائق", status = "تغطية ناقصة", degraded = true,
        ),
    )

    val decision = DecisionSummary(
        topic = "أثر قرار الفائدة القادم على الذهب",
        confidence = 0.35,
        risk = 0.30,
        stance = "محايد",
        recommendation = "لا فتح مركز اتجاهي الآن — الانتظار حتى صدور القرار.",
        conflicts = 2,
        sources = 12,
        qualityFlags = listOf(
            "تضارب غير محسوم بين العائد الحقيقي والتدفق المؤسسي",
            "بوالعلوم يعمل بتغطية ناقصة",
        ),
    )

    val sessions = listOf(
        SessionEntry("التاجر", "تج", 0xFFF39C12, "اليوم 13:00", "تدفقات", 0.66, SessionKind.REPORT),
        SessionEntry("المحلل الاقتصادي", "اق", 0xFF2980B9, "اليوم 11:30", "فائدة", 0.71, SessionKind.REPORT),
        SessionEntry("الوكيل التنسيقي", "قر", 0xFF075E54, "اليوم 11:05", "قرار", 0.35, SessionKind.DECISION),
        SessionEntry("غرفة العاجل", "عا", 0xFFE74C3C, "أمس 16:45", "عاجل", 0.62, SessionKind.ALERT),
        SessionEntry("المحلل السياسي", "سي", 0xFF8E44AD, "أمس 14:00", "جيوسياسة", 0.58, SessionKind.REPORT),
        SessionEntry("بوالعلوم", "بع", 0xFF25D366, "أمس 10:30", "مشاعر", 0.41, SessionKind.REPORT),
    )

    val sources = listOf(
        SourceHealth("the_trader", "market:quotes", true, "يعمل", "8/8 أداة عبر Stooq", 8, false),
        SourceHealth("economic_analyst", "macro:fred", true, "يعمل", "6/6 سلسلة (بلا مفتاح)", 6, false),
        SourceHealth("political_analyst", "news:geo", true, "يعمل", "3/4 خلاصة استجابت", 5, false),
        SourceHealth("breaking_desk", "news:breaking", true, "يعمل", "2/3 خلاصة + بحث موجّه", 6, false),
        SourceHealth("economic_analyst", "macro:worldbank", true, "يعمل", "4 دول", 4, false),
        SourceHealth("abu_aloloum", "social:public", true, "يعمل", "عبر Hacker News", 5, false),
        SourceHealth("abu_aloloum", "social:x", false, "مفتاح غير مضبوط", "X_BEARER_TOKEN غير مضبوط", 0, true),
        SourceHealth("abu_aloloum", "social:youtube", false, "مفتاح غير مضبوط", "YOUTUBE_API_KEY غير مضبوط", 0, true),
    )

    val summary = SourceSummary(
        total = sources.size,
        working = sources.count { it.ok },
        needsKey = sources.count { !it.ok && it.actionable },
        unavailable = sources.count { !it.ok && !it.actionable },
    )
}
