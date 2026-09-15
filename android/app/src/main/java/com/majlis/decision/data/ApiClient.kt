package com.majlis.decision.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * عميل بسيط لخادم «مجلس القرار» (FastAPI).
 *
 * يستخدم HttpURLConnection عمداً بدل مكتبة خارجية: نداءات قليلة وبسيطة
 * لا تستحق اعتمادية إضافية ولا حجماً إضافياً في الحزمة.
 *
 * كل دالة تعيد `null` عند الفشل — والواجهة تسقط إلى بيانات العرض
 * الموسومة بدل أن تتجمّد أو تعرض خطأً غامضاً.
 */
class ApiClient(private val baseUrl: String) {

    private suspend fun get(path: String, timeoutMs: Int = 6000): String? =
        withContext(Dispatchers.IO) {
            var connection: HttpURLConnection? = null
            try {
                connection = (URL("$baseUrl$path").openConnection() as HttpURLConnection).apply {
                    requestMethod = "GET"
                    connectTimeout = timeoutMs
                    readTimeout = timeoutMs
                    setRequestProperty("Accept", "application/json")
                }
                if (connection.responseCode !in 200..299) return@withContext null
                connection.inputStream.bufferedReader().use { it.readText() }
            } catch (_: Exception) {
                null
            } finally {
                connection?.disconnect()
            }
        }

    /** يتحقق من أن الخادم حي ويعيد وضع تشغيله. */
    suspend fun health(): String? {
        val body = get("/api/health", timeoutMs = 4000) ?: return null
        return runCatching { JSONObject(body).optString("mode", "unknown") }.getOrNull()
    }

    /** يقرأ صحة المصادر من GET /api/sources. */
    suspend fun sources(): Pair<SourceSummary, List<SourceHealth>>? {
        val body = get("/api/sources", timeoutMs = 25000) ?: return null
        return runCatching {
            val root = JSONObject(body)
            val summaryJson = root.getJSONObject("summary")
            val summary = SourceSummary(
                total = summaryJson.optInt("total"),
                working = summaryJson.optInt("working"),
                needsKey = summaryJson.optInt("needs_key"),
                unavailable = summaryJson.optInt("unavailable"),
            )
            val array: JSONArray = root.getJSONArray("sources")
            val items = (0 until array.length()).map { index ->
                val item = array.getJSONObject(index)
                SourceHealth(
                    agent = item.optString("agent"),
                    source = item.optString("source"),
                    ok = item.optBoolean("ok"),
                    state = item.optString("state"),
                    detail = item.optString("detail"),
                    evidence = item.optInt("evidence"),
                    actionable = item.optBoolean("actionable"),
                )
            }
            summary to items
        }.getOrNull()
    }

    /** يقرأ آخر قرار تنفيذي. */
    suspend fun latestDecision(): DecisionSummary? {
        val list = get("/api/decisions") ?: return null
        val decisionId = runCatching {
            val array = JSONArray(list)
            if (array.length() == 0) null
            else array.getJSONObject(0).optString("decision_id")
        }.getOrNull() ?: return null

        val body = get("/api/decisions/$decisionId") ?: return null
        return runCatching {
            val root = JSONObject(body)
            val flags = root.optJSONArray("quality_flags")
            DecisionSummary(
                topic = root.optString("topic"),
                confidence = root.optDouble("confidence", 0.0),
                risk = root.optDouble("risk_score", 0.0),
                stance = when (root.optString("stance")) {
                    "bullish" -> "صاعد"
                    "bearish" -> "هابط"
                    else -> "محايد"
                },
                recommendation = root.optString("recommendation"),
                conflicts = root.optJSONArray("conflicts")?.length() ?: 0,
                sources = root.optJSONArray("sources_used")?.length() ?: 0,
                qualityFlags = buildList {
                    for (i in 0 until (flags?.length() ?: 0)) {
                        val text = flags!!.optString(i)
                        // سلسلة حساب الثقة طويلة ولا تصلح لبطاقة مختصرة
                        if (!text.startsWith("سلسلة حساب الثقة")) add(text)
                    }
                },
            )
        }.getOrNull()
    }
}
