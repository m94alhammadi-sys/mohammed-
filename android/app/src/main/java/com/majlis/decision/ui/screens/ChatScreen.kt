package com.majlis.decision.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.majlis.decision.ai.AgentDef
import com.majlis.decision.data.ChatMsg
import com.majlis.decision.ui.components.ArcGauge
import com.majlis.decision.ui.components.InitialsAvatar
import com.majlis.decision.ui.theme.Palette
import com.majlis.decision.ui.theme.Radii

/**
 * شاشة المحادثة — فقاعات بلغة التصميم نفسها: الوارد بطاقة فاتحة،
 * والصادر بلون التمييز الأصفر، ومؤشر «يبحث الآن» أسفل القائمة.
 */
@Composable
fun ChatScreen(
    agent: AgentDef?,
    isWarRoom: Boolean,
    messages: List<ChatMsg>,
    busyAgents: List<AgentDef>,
    canSend: Boolean,
    blockedReason: String,
    onSend: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    var draft by remember { mutableStateOf("") }
    val listState = rememberLazyListState()

    // كل رسالة جديدة تدفع القائمة إلى الأسفل، كما في أي تطبيق محادثة
    LaunchedEffect(messages.size, busyAgents.size) {
        val target = messages.size + if (busyAgents.isEmpty()) 0 else 1
        if (target > 0) listState.animateScrollToItem(target - 1)
    }

    Column(modifier = modifier.fillMaxSize()) {
        LazyColumn(
            state = listState,
            modifier = Modifier.weight(1f).fillMaxWidth(),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(
                start = 14.dp, end = 14.dp, top = 6.dp, bottom = 10.dp,
            ),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            if (messages.isEmpty()) {
                item { EmptyHint(agent, isWarRoom) }
            }

            items(messages, key = { it.id }) { message ->
                MessageBubble(message = message, showAuthor = isWarRoom)
            }

            if (busyAgents.isNotEmpty()) {
                item { TypingRow(busyAgents) }
            }
        }

        Composer(
            draft = draft,
            onDraftChange = { draft = it },
            enabled = canSend,
            blockedReason = blockedReason,
            placeholder = if (isWarRoom) "اكتب الموضوع ليتولّاه المجلس…" else "اكتب سؤالك…",
            onSend = {
                val text = draft.trim()
                if (text.isNotEmpty()) {
                    draft = ""
                    onSend(text)
                }
            },
        )
    }
}

@Composable
private fun EmptyHint(agent: AgentDef?, isWarRoom: Boolean) {
    Column(
        modifier = Modifier.fillMaxWidth().padding(top = 40.dp, start = 12.dp, end = 12.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        InitialsAvatar(
            initials = agent?.initials ?: "قر",
            argb = agent?.colorArgb ?: 0xFF075E54,
            size = 64,
        )
        Spacer(Modifier.height(12.dp))
        Text(
            agent?.name ?: "غرفة القرار",
            color = Palette.TextOnDark, fontSize = 20.sp, fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.height(4.dp))
        Text(
            agent?.role ?: "المجلس كامل — دورة تحليل شاملة",
            color = Palette.TextMutedOnDark, fontSize = 13.sp,
        )
        Spacer(Modifier.height(16.dp))
        Box(
            Modifier.clip(Radii.CardInner).background(Palette.CardDark).padding(14.dp)
        ) {
            Text(
                text = if (isWarRoom)
                    "اكتب موضوعاً، فيبحث كل وكيل في اختصاصه على الإنترنت، " +
                        "ثم يركّب الوكيل التنسيقي قراراً تنفيذياً بثقة ومخاطر وشروط إبطال.\n\n" +
                        "أمثلة:\n• أثر قرار الفائدة القادم على الذهب\n" +
                        "• التوتر في مضيق هرمز وأسعار النفط"
                else
                    "دردشة مباشرة مع هذا الوكيل في حدود اختصاصه وحده. " +
                        "يبحث على الإنترنت عند الحاجة ويذكر مصادره.",
                color = Palette.TextMutedOnDark, fontSize = 13.sp, lineHeight = 21.sp,
            )
        }
    }
}

@Composable
private fun MessageBubble(message: ChatMsg, showAuthor: Boolean) {
    if (message.isSystem) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
            Text(
                message.text,
                color = Palette.TextMutedOnDark,
                fontSize = 12.sp,
                modifier = Modifier
                    .clip(Radii.Pill)
                    .background(Palette.CardDark)
                    .padding(horizontal = 14.dp, vertical = 8.dp),
            )
        }
        return
    }

    val outgoing = message.isOutgoing
    val agent = com.majlis.decision.ai.Agents.byId(message.author)

    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (outgoing) Arrangement.End else Arrangement.Start,
    ) {
        Column(
            modifier = Modifier
                .widthIn(max = 320.dp)
                .clip(
                    RoundedCornerShape(
                        topStart = 20.dp, topEnd = 20.dp,
                        bottomStart = if (outgoing) 20.dp else 6.dp,
                        bottomEnd = if (outgoing) 6.dp else 20.dp,
                    )
                )
                .background(
                    when {
                        outgoing -> Palette.Accent
                        message.kind == "decision" -> Palette.CardWhite
                        else -> Palette.CardLight
                    }
                )
                .padding(horizontal = 13.dp, vertical = 10.dp),
        ) {
            if (!outgoing && showAuthor && agent != null) {
                Text(
                    agent.name,
                    color = Color(agent.colorArgb),
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                )
                Spacer(Modifier.height(3.dp))
            }

            if (message.kind == "decision" && message.confidence != null) {
                ArcGauge(
                    value = message.confidence,
                    caption = "ثقة القرار",
                    modifier = Modifier.fillMaxWidth().height(96.dp),
                )
                Spacer(Modifier.height(10.dp))
            }

            Text(
                text = message.text,
                color = Palette.TextPrimary,
                fontSize = 14.sp,
                lineHeight = 21.sp,
            )

            val chips = buildList {
                message.confidence?.let { add("ثقة ${(it * 100).toInt()}%") }
                message.evidence?.takeIf { it > 0 }?.let { add("$it مصدر") }
                if (message.degraded) add("بلا بحث حي")
            }
            if (chips.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    chips.forEach { chip ->
                        Text(
                            chip,
                            color = Palette.TextMuted,
                            fontSize = 10.sp,
                            modifier = Modifier
                                .clip(Radii.Pill)
                                .background(Palette.Background.copy(alpha = 0.18f))
                                .padding(horizontal = 8.dp, vertical = 3.dp),
                        )
                    }
                }
            }

            Spacer(Modifier.height(4.dp))
            Text(
                text = message.ts.substringAfter('T').take(5),
                color = Palette.TextMuted,
                fontSize = 10.sp,
                modifier = Modifier.align(Alignment.End),
            )
        }
    }
}

@Composable
private fun TypingRow(agents: List<AgentDef>) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        agents.take(3).forEach { agent ->
            Row(
                modifier = Modifier
                    .clip(Radii.Pill)
                    .background(Palette.CardLight)
                    .padding(horizontal = 10.dp, vertical = 7.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(Modifier.size(7.dp).clip(CircleShape).background(Color(agent.colorArgb)))
                Spacer(Modifier.size(6.dp))
                Text(
                    "${agent.name} يبحث…",
                    color = Palette.TextPrimary, fontSize = 11.sp,
                )
            }
        }
        if (agents.size > 3) {
            Text(
                "+${agents.size - 3}",
                color = Palette.TextMutedOnDark, fontSize = 11.sp,
                modifier = Modifier.align(Alignment.CenterVertically),
            )
        }
    }
}

@Composable
private fun Composer(
    draft: String,
    onDraftChange: (String) -> Unit,
    enabled: Boolean,
    blockedReason: String,
    placeholder: String,
    onSend: () -> Unit,
) {
    Column(Modifier.fillMaxWidth()) {
        if (!enabled && blockedReason.isNotBlank()) {
            Text(
                blockedReason,
                color = Palette.Accent,
                fontSize = 12.sp,
                lineHeight = 18.sp,
                modifier = Modifier
                    .fillMaxWidth()
                    .background(Palette.CardDark)
                    .padding(horizontal = 16.dp, vertical = 10.dp),
            )
        }

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(Palette.BackgroundDeep)
                .padding(horizontal = 12.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            TextField(
                value = draft,
                onValueChange = onDraftChange,
                enabled = enabled,
                modifier = Modifier.weight(1f),
                placeholder = {
                    Text(placeholder, color = Palette.TextMuted, fontSize = 14.sp)
                },
                textStyle = LocalTextStyle.current.copy(fontSize = 14.sp),
                shape = Radii.Pill,
                maxLines = 4,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(onSend = { onSend() }),
                colors = TextFieldDefaults.colors(
                    focusedContainerColor = Palette.CardWhite,
                    unfocusedContainerColor = Palette.CardLight,
                    disabledContainerColor = Palette.CardLight.copy(alpha = 0.5f),
                    focusedTextColor = Palette.TextPrimary,
                    unfocusedTextColor = Palette.TextPrimary,
                    disabledTextColor = Palette.TextMuted,
                    focusedIndicatorColor = Color.Transparent,
                    unfocusedIndicatorColor = Color.Transparent,
                    disabledIndicatorColor = Color.Transparent,
                    cursorColor = Palette.TextPrimary,
                ),
            )

            Box(
                modifier = Modifier
                    .size(46.dp)
                    .clip(CircleShape)
                    .background(if (enabled) Palette.Accent else Palette.CardLight.copy(alpha = 0.4f))
                    .then(if (enabled) Modifier.clickable { onSend() } else Modifier),
                contentAlignment = Alignment.Center,
            ) {
                Text("➤", fontSize = 17.sp, color = Palette.TextPrimary)
            }
        }
    }
}