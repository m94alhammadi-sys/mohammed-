package com.majlis.decision

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBars
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshots.SnapshotStateList
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.majlis.decision.ai.AgentDef
import com.majlis.decision.ai.AgentEngine
import com.majlis.decision.ai.Agents
import com.majlis.decision.data.ChatMsg
import com.majlis.decision.data.Prefs
import com.majlis.decision.ui.components.CircleButton
import com.majlis.decision.ui.components.InitialsAvatar
import com.majlis.decision.ui.screens.ChatListScreen
import com.majlis.decision.ui.screens.ChatScreen
import com.majlis.decision.ui.screens.SettingsDialog
import com.majlis.decision.ui.theme.MajlisTheme
import com.majlis.decision.ui.theme.Palette
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        setContent {
            MajlisTheme {
                // التطبيق عربي بالكامل: اتجاه من اليمين إلى اليسار
                CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) {
                    MajlisApp()
                }
            }
        }
    }
}

/**
 * حالة التطبيق: المحادثات في الذاكرة، والوكلاء يعملون عبر Claude مباشرة
 * بلا خادم وسيط.
 */
class MajlisViewModel(private val prefs: Prefs) : ViewModel() {

    private val engine = AgentEngine(prefs)

    /** رسائل كل محادثة، مفتاحها معرّف الوكيل أو `war_room`. */
    val threads = mutableStateMapOf<String, SnapshotStateList<ChatMsg>>()

    var busy by mutableStateOf<List<AgentDef>>(emptyList())
        private set
    var apiKey by mutableStateOf(prefs.apiKey)
        private set
    var model by mutableStateOf(prefs.model)
        private set
    var searchEnabled by mutableStateOf(prefs.webSearch)
        private set

    val isConfigured: Boolean get() = apiKey.isNotBlank()

    fun thread(chatId: String): SnapshotStateList<ChatMsg> =
        threads.getOrPut(chatId) { mutableStateListOf() }

    fun saveSettings(key: String, chosenModel: String, search: Boolean) {
        prefs.apiKey = key
        prefs.model = chosenModel
        prefs.webSearch = search
        apiKey = key
        model = chosenModel
        searchEnabled = search
    }

    /** إرسال رسالة: دردشة فردية أو دورة مجلس كاملة. */
    fun send(chatId: String, text: String) {
        val messages = thread(chatId)
        messages += ChatMsg(
            id = "u_${System.nanoTime()}", chatId = chatId, author = "user",
            text = text, ts = now(),
        )

        viewModelScope.launch {
            if (chatId == Agents.WAR_ROOM) runCycle(text, messages)
            else runChat(chatId, messages)
        }
    }

    private suspend fun runChat(chatId: String, messages: SnapshotStateList<ChatMsg>) {
        val agent = Agents.byId(chatId) ?: return
        busy = listOf(agent)
        try {
            messages += engine.chat(agent, messages.toList())
        } finally {
            busy = emptyList()
        }
    }

    private suspend fun runCycle(topic: String, messages: SnapshotStateList<ChatMsg>) {
        val working = mutableListOf<AgentDef>()
        try {
            engine.runCycle(topic) { progress ->
                when (progress) {
                    is AgentEngine.Progress.Working -> {
                        working += progress.agent
                        busy = working.toList()
                    }
                    is AgentEngine.Progress.Reported -> {
                        messages += progress.message
                        working.removeAll { it.id == progress.message.author }
                        busy = working.toList()
                    }
                    is AgentEngine.Progress.Decision -> {
                        messages += progress.message
                        working.clear()
                        busy = emptyList()
                    }
                    is AgentEngine.Progress.Failed -> {
                        messages += ChatMsg(
                            id = "e_${System.nanoTime()}", chatId = Agents.WAR_ROOM,
                            author = progress.agent.id,
                            text = "${progress.agent.name}: ${progress.reason}",
                            ts = now(), kind = "system",
                        )
                        working.removeAll { it.id == progress.agent.id }
                        busy = working.toList()
                    }
                }
            }
        } finally {
            busy = emptyList()
        }
    }

    private fun now(): String =
        SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US).format(Date())

    class Factory(private val prefs: Prefs) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T =
            MajlisViewModel(prefs) as T
    }
}

@Composable
fun MajlisApp() {
    val context = LocalContext.current
    val prefs = remember { Prefs(context) }
    val viewModel: MajlisViewModel = viewModel(factory = MajlisViewModel.Factory(prefs))

    var openChat by remember { mutableStateOf<String?>(null) }
    var showSettings by remember { mutableStateOf(false) }

    // أول تشغيل بلا مفتاح: نفتح الإعدادات مباشرة بدل ترك المستخدم أمام تطبيق صامت
    LaunchedEffect(Unit) {
        if (!viewModel.isConfigured) showSettings = true
    }

    BackHandler(enabled = openChat != null) { openChat = null }

    val insets = WindowInsets.systemBars.asPaddingValues()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(listOf(Palette.Background, Palette.BackgroundDeep)))
            .padding(top = insets.calculateTopPadding(), bottom = insets.calculateBottomPadding())
            .imePadding()
    ) {
        val chatId = openChat
        val agent = chatId?.let { Agents.byId(it) }
        val isWarRoom = chatId == Agents.WAR_ROOM

        TopBar(
            title = when {
                chatId == null -> "مجلس القرار"
                isWarRoom -> "غرفة القرار"
                else -> agent?.name ?: ""
            },
            subtitle = when {
                chatId == null -> if (viewModel.isConfigured) "متصل — ${viewModel.model}"
                else "غير مهيّأ — أضف مفتاحك"
                isWarRoom -> "${Agents.SPECIALISTS.size} وكلاء + التنسيقي"
                else -> agent?.role ?: ""
            },
            agent = agent,
            showBack = chatId != null,
            onBack = { openChat = null },
            onSettings = { showSettings = true },
        )

        Box(Modifier.weight(1f)) {
            if (chatId == null) {
                ChatListScreen(
                    lastMessages = viewModel.threads.mapValues { (_, messages) ->
                        messages.lastOrNull()?.text?.replace("\n", " ")?.take(60).orEmpty()
                    }.filterValues { it.isNotBlank() },
                    unread = emptyMap(),
                    onOpen = { openChat = it },
                )
            } else {
                ChatScreen(
                    agent = agent,
                    isWarRoom = isWarRoom,
                    messages = viewModel.thread(chatId),
                    busyAgents = viewModel.busy,
                    canSend = viewModel.isConfigured && viewModel.busy.isEmpty(),
                    blockedReason = when {
                        !viewModel.isConfigured ->
                            "أضف مفتاح Anthropic من الإعدادات (⚙) ليتمكن الوكلاء من البحث والتحليل."
                        viewModel.busy.isNotEmpty() -> "الوكلاء يعملون الآن…"
                        else -> ""
                    },
                    onSend = { viewModel.send(chatId, it) },
                )
            }
        }
    }

    if (showSettings) {
        SettingsDialog(
            initialKey = viewModel.apiKey,
            initialModel = viewModel.model,
            initialSearch = viewModel.searchEnabled,
            onSave = { key, chosenModel, search ->
                viewModel.saveSettings(key, chosenModel, search)
                showSettings = false
            },
            onDismiss = { showSettings = false },
        )
    }
}

@Composable
private fun TopBar(
    title: String,
    subtitle: String,
    agent: AgentDef?,
    showBack: Boolean,
    onBack: () -> Unit,
    onSettings: () -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        if (showBack) {
            CircleButton(label = "›", onClick = onBack, size = 40)
        }
        if (agent != null) {
            InitialsAvatar(agent.initials, agent.colorArgb, size = 40)
        }
        Column(Modifier.weight(1f)) {
            Text(
                title, color = Palette.TextOnDark,
                fontSize = if (showBack) 18.sp else 22.sp,
                fontWeight = FontWeight.SemiBold, maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                subtitle, color = Palette.TextMutedOnDark, fontSize = 11.sp,
                maxLines = 1, overflow = TextOverflow.Ellipsis,
            )
        }
        CircleButton(label = "⚙", onClick = onSettings, size = 40)
    }
}
