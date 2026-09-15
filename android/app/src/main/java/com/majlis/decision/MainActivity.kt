package com.majlis.decision

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBars
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.majlis.decision.data.ApiClient
import com.majlis.decision.data.DecisionSummary
import com.majlis.decision.data.DemoData
import com.majlis.decision.data.LoadState
import com.majlis.decision.data.SourceHealth
import com.majlis.decision.data.SourceSummary
import com.majlis.decision.ui.components.CircleButton
import com.majlis.decision.ui.components.PillButton
import com.majlis.decision.ui.screens.AgentsScreen
import com.majlis.decision.ui.screens.DecisionScreen
import com.majlis.decision.ui.screens.SourcesScreen
import com.majlis.decision.ui.theme.MajlisTheme
import com.majlis.decision.ui.theme.Palette
import kotlinx.coroutines.launch

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

enum class Tab(val label: String) {
    AGENTS("الوكلاء"),
    SOURCES("المصادر"),
    DECISION("القرار"),
}

/**
 * حالة التطبيق: يحاول الاتصال بخادم «مجلس القرار»، وعند تعذّره يعرض
 * بيانات توضيحية **موسومة صراحةً** بدل التجمّد أو خطأ غامض.
 */
class MajlisViewModel : ViewModel() {
    var state by mutableStateOf<LoadState>(LoadState.Idle)
        private set
    var decision by mutableStateOf(DemoData.decision)
        private set
    var summary by mutableStateOf(DemoData.summary)
        private set
    var sources by mutableStateOf(DemoData.sources)
        private set

    fun refresh(server: String = BuildConfig.DEFAULT_SERVER) {
        if (state is LoadState.Loading) return
        state = LoadState.Loading
        viewModelScope.launch {
            val client = ApiClient(server.trimEnd('/'))
            val mode = client.health()
            if (mode == null) {
                state = LoadState.Demo("الخادم غير متاح على $server")
                return@launch
            }
            client.latestDecision()?.let { decision = it }
            client.sources()?.let { (loadedSummary, loadedSources) ->
                summary = loadedSummary
                sources = loadedSources
            }
            state = LoadState.Live(server)
        }
    }
}

@Composable
fun MajlisApp(viewModel: MajlisViewModel = viewModel()) {
    var tab by remember { mutableStateOf(Tab.AGENTS) }
    var selectedAgents by remember { mutableStateOf(setOf(DemoData.agents[1].id)) }

    LaunchedEffect(Unit) { viewModel.refresh() }

    val insets = WindowInsets.systemBars.asPaddingValues()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(listOf(Palette.Background, Palette.BackgroundDeep))
            )
            .padding(
                top = insets.calculateTopPadding(),
                bottom = insets.calculateBottomPadding(),
            )
    ) {
        TopBar(
            active = tab,
            onSelect = { tab = it },
            onRefresh = { viewModel.refresh() },
            busy = viewModel.state is LoadState.Loading,
        )

        ModeBanner(viewModel.state)

        Box(Modifier.weight(1f)) {
            when (tab) {
                Tab.AGENTS -> AgentsScreen(
                    agents = DemoData.agents,
                    selected = selectedAgents,
                    onToggle = { id ->
                        selectedAgents =
                            if (id in selectedAgents) selectedAgents - id else selectedAgents + id
                    },
                )

                Tab.SOURCES -> SourcesScreen(
                    summary = viewModel.summary,
                    sources = viewModel.sources,
                )

                Tab.DECISION -> DecisionScreen(
                    decision = viewModel.decision,
                    sessions = DemoData.sessions,
                )
            }
        }
    }
}

@Composable
private fun TopBar(
    active: Tab,
    onSelect: (Tab) -> Unit,
    onRefresh: () -> Unit,
    busy: Boolean,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 18.dp, vertical = 12.dp)
            .horizontalScroll(rememberScrollState()),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        CircleButton(label = "→", onClick = onRefresh)
        Spacer(Modifier.size(4.dp))
        Tab.entries.forEach { entry ->
            PillButton(
                text = entry.label,
                selected = entry == active,
                onClick = { onSelect(entry) },
            )
        }
        CircleButton(label = if (busy) "◌" else "⟳", onClick = onRefresh)
    }
}

/** شريط يوضّح مصدر البيانات: خادم حي أم عرض توضيحي. */
@Composable
private fun ModeBanner(state: LoadState) {
    val (text, accent) = when (state) {
        is LoadState.Live -> "متصل بالخادم — بيانات حية" to true
        is LoadState.Loading -> "جارٍ الاتصال بالخادم…" to false
        is LoadState.Demo -> "عرض توضيحي — ${state.reason}" to false
        LoadState.Idle -> "غير متصل" to false
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 18.dp)
            .padding(bottom = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier
                .size(8.dp)
                .background(
                    color = if (accent) Palette.Accent else Palette.TextMutedOnDark,
                    shape = androidx.compose.foundation.shape.CircleShape,
                )
        )
        Spacer(Modifier.size(8.dp))
        Text(
            text = text,
            color = Palette.TextOnDark.copy(alpha = 0.8f),
            fontSize = 11.sp,
            fontWeight = FontWeight.Medium,
        )
    }
}
