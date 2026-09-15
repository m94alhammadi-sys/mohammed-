package com.majlis.decision.data

import android.content.Context

/**
 * إعدادات محفوظة على الجهاز.
 *
 * مفتاح Anthropic هو ما يجعل التطبيق مستقلاً: يتصل بالإنترنت ويبحث
 * ويحلل بنفسه بلا خادم وسيط. المفتاح **مفتاح المستخدم** ويبقى على
 * جهازه — لا يُرسل إلى أي جهة غير Anthropic، ولا يوجد مفتاح مضمّن
 * في التطبيق.
 */
class Prefs(context: Context) {

    private val store = context.getSharedPreferences("majlis", Context.MODE_PRIVATE)

    /** مفتاح Anthropic الخاص بالمستخدم. فارغ = التطبيق لا يستطيع التحليل. */
    var apiKey: String
        get() = store.getString(KEY_API, "") ?: ""
        set(value) = store.edit().putString(KEY_API, value.trim()).apply()

    /** النموذج المستخدم. */
    var model: String
        get() = store.getString(KEY_MODEL, DEFAULT_MODEL) ?: DEFAULT_MODEL
        set(value) = store.edit().putString(KEY_MODEL, value).apply()

    /** تفعيل البحث الحي على الإنترنت أثناء التحليل. */
    var webSearch: Boolean
        get() = store.getBoolean(KEY_SEARCH, true)
        set(value) = store.edit().putBoolean(KEY_SEARCH, value).apply()

    val isConfigured: Boolean get() = apiKey.isNotBlank()

    companion object {
        private const val KEY_API = "anthropic_api_key"
        private const val KEY_MODEL = "model"
        private const val KEY_SEARCH = "web_search"

        const val DEFAULT_MODEL = "claude-opus-5"

        /** النماذج المعروضة للاختيار، من الأقوى إلى الأخف. */
        val MODELS = listOf(
            "claude-opus-5" to "Opus 5 — الأقوى تحليلاً",
            "claude-sonnet-5" to "Sonnet 5 — متوازن",
            "claude-haiku-4-5" to "Haiku 4.5 — الأسرع والأرخص",
        )
    }
}
