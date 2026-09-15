package com.majlis.decision.ai

import com.majlis.decision.data.Prefs
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * اتصال مباشر بواجهة Claude — هذا ما يجعل التطبيق مستقلاً بلا خادم وسيط.
 *
 * البحث الحي يتم عبر **أداة البحث الخادمية** (`web_search`): تعمل على
 * خوادم Anthropic، فلا نحتاج مفتاح بحث منفصل ولا حلقة تنفيذ في التطبيق،
 * وتصلنا نتائجها كأدلة موثّقة بروابطها.
 */
class AnthropicClient(private val prefs: Prefs) {

    private val http = OkHttpClient.Builder()
        // التحليل العميق مع البحث قد يستغرق دقائق — مهلة قراءة سخية
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(300, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .build()

    /** نتيجة استدعاء واحد: نص + الأدلة التي عادت من البحث. */
    data class Result(
        val text: String,
        val sources: List<Source> = emptyList(),
        val searched: Boolean = false,
        val error: String? = null,
    ) {
        val ok: Boolean get() = error == null
    }

    data class Source(val title: String, val url: String, val publisher: String)

    /**
     * يرسل محادثة ويعيد رد Claude.
     *
     * @param system برومبت النظام (اختصاص الوكيل وحدوده)
     * @param messages تاريخ المحادثة بصيغة [{role, content}]
     * @param effort عمق التفكير: low | medium | high | xhigh
     * @param allowSearch تفعيل البحث الحي
     * @param domains نطاقات يُفضَّل البحث ضمنها (تُمرَّر للأداة)
     */
    suspend fun send(
        system: String,
        messages: List<Pair<String, String>>,
        effort: String = "medium",
        allowSearch: Boolean = true,
        domains: List<String> = emptyList(),
        maxTokens: Int = 8000,
    ): Result = withContext(Dispatchers.IO) {
        val key = prefs.apiKey
        if (key.isBlank()) {
            return@withContext Result("", error = "لم يُضبط مفتاح Anthropic. افتح الإعدادات وأضفه.")
        }

        val body = JSONObject().apply {
            put("model", prefs.model)
            put("max_tokens", maxTokens)
            put("system", JSONArray().put(JSONObject().apply {
                put("type", "text")
                put("text", system)
                // البرومبتات طويلة وثابتة — تخزينها مؤقتاً يخفض التكلفة كثيراً
                put("cache_control", JSONObject().put("type", "ephemeral"))
            }))
            put("messages", JSONArray().apply {
                messages.forEach { (role, content) ->
                    put(JSONObject().put("role", role).put("content", content))
                }
            })
            put("thinking", JSONObject().put("type", "adaptive"))
            put("output_config", JSONObject().put("effort", effort))

            if (allowSearch && prefs.webSearch) {
                val tool = JSONObject().apply {
                    put("type", "web_search_20260209")
                    put("name", "web_search")
                    put("max_uses", 6)
                    if (domains.isNotEmpty()) {
                        put("allowed_domains", JSONArray().apply { domains.forEach { put(it) } })
                    }
                }
                put("tools", JSONArray().put(tool))
            }
        }

        val request = Request.Builder()
            .url("https://api.anthropic.com/v1/messages")
            .addHeader("x-api-key", key)
            .addHeader("anthropic-version", "2023-06-01")
            .addHeader("content-type", "application/json")
            .post(body.toString().toRequestBody(JSON))
            .build()

        try {
            http.newCall(request).execute().use { response ->
                val raw = response.body?.string().orEmpty()
                if (!response.isSuccessful) {
                    return@withContext Result("", error = friendlyError(response.code, raw))
                }
                parse(JSONObject(raw))
            }
        } catch (exc: Exception) {
            Result("", error = "تعذّر الاتصال: ${exc.message ?: exc.javaClass.simpleName}")
        }
    }

    private fun parse(root: JSONObject): Result {
        // فحص سبب التوقف قبل قراءة المحتوى: الرفض والانقطاع يُعالَجان لا يُتجاهلان
        when (root.optString("stop_reason")) {
            "refusal" -> return Result("", error = "رفض النموذج تنفيذ هذا الطلب.")
            "max_tokens" -> { /* نص منقوص — نعرضه مع تنبيه أدناه */ }
        }

        val text = StringBuilder()
        val sources = mutableListOf<Source>()
        var searched = false

        val content = root.optJSONArray("content") ?: JSONArray()
        for (i in 0 until content.length()) {
            val block = content.optJSONObject(i) ?: continue
            when (block.optString("type")) {
                "text" -> text.append(block.optString("text"))
                "web_search_tool_result" -> {
                    searched = true
                    // عند فشل الأداة يعود المحتوى كائن خطأ لا قائمة
                    val items = block.optJSONArray("content") ?: continue
                    for (j in 0 until items.length()) {
                        val item = items.optJSONObject(j) ?: continue
                        if (item.optString("type") != "web_search_result") continue
                        val url = item.optString("url")
                        sources += Source(
                            title = item.optString("title").ifBlank { url },
                            url = url,
                            publisher = hostOf(url),
                        )
                    }
                }
            }
        }

        if (root.optString("stop_reason") == "max_tokens") {
            text.append("\n\n(انقطع الرد عند حد الطول.)")
        }

        return Result(text.toString().trim(), sources.distinctBy { it.url }, searched)
    }

    private fun friendlyError(code: Int, raw: String): String {
        val detail = runCatching {
            JSONObject(raw).optJSONObject("error")?.optString("message").orEmpty()
        }.getOrDefault("")
        return when (code) {
            401 -> "مفتاح غير صالح. تحقق من المفتاح في الإعدادات."
            403 -> "المفتاح لا يملك صلاحية لهذا الطلب."
            404 -> "النموذج غير متاح لحسابك: ${prefs.model}"
            429 -> "تجاوزت حد الطلبات. انتظر قليلاً ثم أعد المحاولة."
            in 500..599 -> "خطأ مؤقت في الخدمة ($code). أعد المحاولة."
            else -> "فشل الطلب ($code)${if (detail.isNotBlank()) ": $detail" else ""}"
        }
    }

    private fun hostOf(url: String): String = runCatching {
        java.net.URI(url).host?.removePrefix("www.") ?: "مصدر"
    }.getOrDefault("مصدر")

    companion object {
        private val JSON = "application/json; charset=utf-8".toMediaType()
    }
}
