package com.majlis.decision.data

/** وكيل متخصص كما يُعرض في قائمة «الوكلاء». */
data class Agent(
    val id: String,
    val name: String,
    val role: String,
    val initials: String,
    val accentArgb: Long,
    val specialty: String,
    val sources: String,
    val confidence: Double,
    val lastReport: String,
    val status: String,
    val degraded: Boolean = false,
    val selected: Boolean = false,
)

/** حالة موصل بيانات واحد — مطابقة لمخرج GET /api/sources. */
data class SourceHealth(
    val agent: String,
    val source: String,
    val ok: Boolean,
    val state: String,
    val detail: String,
    val evidence: Int,
    val actionable: Boolean,
)

/** ملخص فحص المصادر. */
data class SourceSummary(
    val total: Int,
    val working: Int,
    val needsKey: Int,
    val unavailable: Int,
)

/** سطر في سجل التقارير/الجلسات. */
data class SessionEntry(
    val agentName: String,
    val initials: String,
    val accentArgb: Long,
    val timestamp: String,
    val place: String,
    val confidence: Double,
    val kind: SessionKind,
)

enum class SessionKind { REPORT, DECISION, ALERT }

/** التقرير التنفيذي المختصر. */
data class DecisionSummary(
    val topic: String,
    val confidence: Double,
    val risk: Double,
    val stance: String,
    val recommendation: String,
    val conflicts: Int,
    val sources: Int,
    val qualityFlags: List<String>,
)

/** حالة الاتصال بالخادم. */
sealed interface LoadState {
    data object Idle : LoadState
    data object Loading : LoadState
    data class Live(val server: String) : LoadState
    data class Demo(val reason: String) : LoadState
}
