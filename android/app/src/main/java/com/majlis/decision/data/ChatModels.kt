package com.majlis.decision.data

/** دردشة في القائمة: وكيل واحد أو غرفة القرار الجماعية. */
data class ChatSummary(
    val id: String,
    val name: String,
    val avatar: String,
    val colorArgb: Long,
    val tagline: String,
    val isGroup: Boolean,
    val lastMessage: String = "",
    val lastTs: String = "",
)

/** رسالة واحدة — مطابقة لـ ChatMessage في الخادم. */
data class ChatMsg(
    val id: String,
    val chatId: String,
    val author: String,
    val text: String,
    val ts: String,
    val kind: String = "text",
    val confidence: Double? = null,
    val risk: Double? = null,
    val evidence: Int? = null,
    val degraded: Boolean = false,
) {
    val isOutgoing: Boolean get() = author == "user"
    val isSystem: Boolean get() = kind == "system"
}
