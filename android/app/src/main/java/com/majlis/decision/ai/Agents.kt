package com.majlis.decision.ai

/** تعريف وكيل: هويته وبرومبته ونطاقات بحثه المفضّلة. */
data class AgentDef(
    val id: String,
    val name: String,
    val role: String,
    val initials: String,
    val colorArgb: Long,
    val prompt: String,
    /** نطاقات يُقيَّد بها بحثه — تفرض فصل الاختصاص على مستوى المصادر. */
    val domains: List<String> = emptyList(),
)

object Agents {

    val BREAKING = AgentDef(
        id = "breaking_desk", name = "غرفة العاجل", role = "الأحداث الطارئة لحظة بلحظة",
        initials = "عا", colorArgb = 0xFFE74C3C, prompt = Prompts.BREAKING,
        domains = listOf("reuters.com", "apnews.com", "bbc.com", "aljazeera.net"),
    )

    val GEO = AgentDef(
        id = "political_analyst", name = "المحلل السياسي", role = "الجيوسياسة وقرارات الحكومات",
        initials = "سي", colorArgb = 0xFF8E44AD, prompt = Prompts.GEO,
        domains = listOf("reuters.com", "apnews.com", "aljazeera.net", "un.org", "europa.eu"),
    )

    val MACRO = AgentDef(
        id = "economic_analyst", name = "المحلل الاقتصادي", role = "التضخم والفائدة والبنوك المركزية",
        initials = "اق", colorArgb = 0xFF2980B9, prompt = Prompts.MACRO,
        domains = listOf("federalreserve.gov", "ecb.europa.eu", "imf.org", "bls.gov", "bis.org"),
    )

    val FLOW = AgentDef(
        id = "the_trader", name = "التاجر", role = "تدفقات السيولة وحركة الحيتان",
        initials = "تج", colorArgb = 0xFFF39C12, prompt = Prompts.FLOW,
        domains = listOf("sec.gov", "reuters.com", "bloomberg.com", "cftc.gov"),
    )

    val SOCIAL = AgentDef(
        id = "abu_aloloum", name = "بوالعلوم", role = "مشاعر الجمهور والمواضيع الرائجة",
        initials = "بع", colorArgb = 0xFF25D366, prompt = Prompts.SOCIAL,
        domains = listOf("reddit.com", "x.com", "linkedin.com", "youtube.com"),
    )

    val CHIEF = AgentDef(
        id = "chief", name = "الوكيل التنسيقي", role = "يربط الخيوط ويصنع القرار",
        initials = "قر", colorArgb = 0xFF075E54, prompt = Prompts.CHIEF,
        // التنسيقي بلا نطاقات: مصدره تقارير الوكلاء لا الإنترنت — مُركِّب لا مصدر
    )

    /** المتخصصون بترتيب التشغيل: العاجل أولاً لأنه قد يغيّر إطار التحليل. */
    val SPECIALISTS = listOf(BREAKING, GEO, MACRO, FLOW, SOCIAL)

    /** كل من يمكن محادثته، بما فيهم التنسيقي. */
    val ALL = SPECIALISTS + CHIEF

    fun byId(id: String): AgentDef? = ALL.firstOrNull { it.id == id }

    const val WAR_ROOM = "war_room"
}
