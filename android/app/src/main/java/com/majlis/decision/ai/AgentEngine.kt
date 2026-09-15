package com.majlis.decision.ai

import com.majlis.decision.data.ChatMsg
import com.majlis.decision.data.Prefs
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * محرّك الوكلاء داخل التطبيق.
 *
 * وضعان:
 *  - **دردشة مباشرة**: سؤال إلى وكيل واحد، يبحث ويجيب في حدود اختصاصه.
 *  - **دورة المجلس**: توزيع متوازٍ على الوكلاء الخمسة، ثم تركيب القرار
 *    لدى الوكيل التنسيقي الذي لا يملك بحثاً خاصاً به — مصدره تقاريرهم.
 */
class AgentEngine(private val prefs: Prefs) {

    private val client = AnthropicClient(prefs)

    /** بلاغ تقدّم يُغذّي الواجهة أثناء الدورة. */
    sealed interface Progress {
        data class Working(val agent: AgentDef) : Progress
        data class Reported(val message: ChatMsg) : Progress
        data class Failed(val agent: AgentDef, val reason: String) : Progress
        data class Decision(val message: ChatMsg) : Progress
    }

    // ------------------------------------------------------------ دردشة

    /** يرد وكيل واحد على محادثة جارية. */
    suspend fun chat(agent: AgentDef, history: List<ChatMsg>): ChatMsg {
        val turns = history
            .filter { !it.isSystem }
            .takeLast(16)
            .map { (if (it.isOutgoing) "user" else "assistant") to it.text }

        // الواجهة تمنع الإرسال بلا رسالة مستخدم، لكن نحرس الحالة الحدّية
        val safeTurns = if (turns.none { it.first == "user" }) {
            listOf("user" to (history.lastOrNull()?.text ?: "ابدأ"))
        } else turns

        val result = client.send(
            system = Prompts.forChat(agent.prompt),
            messages = safeTurns,
            effort = "medium",
            allowSearch = agent.domains.isNotEmpty(),
            domains = agent.domains,
        )

        return toMessage(agent, result, chatId = agent.id, kind = "text")
    }

    // ------------------------------------------------------------ دورة

    /**
     * دورة مجلس كاملة: الوكلاء بالتوازي ثم التركيب.
     * يستدعي [onProgress] عند كل خطوة ليظهر التقدّم لحظياً.
     */
    suspend fun runCycle(topic: String, onProgress: suspend (Progress) -> Unit) {
        val reports = coroutineScope {
            Agents.SPECIALISTS.map { agent ->
                async {
                    onProgress(Progress.Working(agent))
                    val result = client.send(
                        system = Prompts.forCycle(agent.prompt),
                        messages = listOf("user" to "الموضوع قيد التحليل:\n$topic"),
                        effort = "high",
                        allowSearch = true,
                        domains = agent.domains,
                        maxTokens = 4000,
                    )
                    if (!result.ok) {
                        onProgress(Progress.Failed(agent, result.error ?: "سبب غير معروف"))
                        return@async null
                    }
                    val message = toMessage(agent, result, Agents.WAR_ROOM, kind = "report")
                    onProgress(Progress.Reported(message))
                    agent to result
                }
            }.awaitAll()
        }.filterNotNull()

        if (reports.isEmpty()) {
            onProgress(Progress.Failed(Agents.CHIEF, "لم يُكمل أي وكيل تقريره، فلا أساس للقرار."))
            return
        }

        onProgress(Progress.Working(Agents.CHIEF))

        val brief = buildString {
            append("الموضوع: $topic\n\n")
            append("# تقارير الوكلاء\n")
            reports.forEach { (agent, result) ->
                append("\n## ${agent.name} (${agent.role})\n")
                append(result.text.trim())
                if (result.sources.isNotEmpty()) {
                    append("\nمصادره: ")
                    append(result.sources.take(5).joinToString("، ") { it.publisher })
                }
                append("\n")
            }
            val missing = Agents.SPECIALISTS.filter { spec -> reports.none { it.first.id == spec.id } }
            if (missing.isNotEmpty()) {
                append("\n# وكلاء لم يسلّموا تقاريرهم (نقص تغطية يجب أن يخفض ثقتك)\n")
                missing.forEach { append("- ${it.name}: ${it.role}\n") }
            }
        }

        val decision = client.send(
            system = "${Prompts.SHARED}\n\n${Prompts.CHIEF}",
            messages = listOf("user" to brief),
            effort = "xhigh",
            allowSearch = false,   // التنسيقي مُركِّب لا مصدر
            maxTokens = 8000,
        )

        if (!decision.ok) {
            onProgress(Progress.Failed(Agents.CHIEF, decision.error ?: "فشل التركيب"))
            return
        }

        onProgress(
            Progress.Decision(
                toMessage(Agents.CHIEF, decision, Agents.WAR_ROOM, kind = "decision")
            )
        )
    }

    // ------------------------------------------------------------ مساعد

    private fun toMessage(
        agent: AgentDef,
        result: AnthropicClient.Result,
        chatId: String,
        kind: String,
    ): ChatMsg {
        val body = if (result.ok) {
            buildString {
                append(result.text)
                if (result.sources.isNotEmpty()) {
                    append("\n\n*المصادر*\n")
                    result.sources.take(6).forEach { append("• ${it.publisher} — ${it.url}\n") }
                }
            }.trim()
        } else {
            "تعذّر إنتاج رد: ${result.error}"
        }

        return ChatMsg(
            id = "m_${System.nanoTime()}",
            chatId = chatId,
            author = agent.id,
            text = body,
            ts = timestamp(),
            kind = if (result.ok) kind else "system",
            confidence = extractConfidence(result.text),
            evidence = result.sources.size,
            degraded = !result.searched && agent.domains.isNotEmpty(),
        )
    }

    /** يلتقط «الثقة: NN%» من نص الرد. */
    private fun extractConfidence(text: String): Double? {
        val match = Regex("الثقة\\s*[:：]\\s*(\\d{1,3})\\s*%").find(text) ?: return null
        return match.groupValues[1].toIntOrNull()?.coerceIn(0, 100)?.div(100.0)
    }

    private fun timestamp(): String =
        SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US).format(Date())
}