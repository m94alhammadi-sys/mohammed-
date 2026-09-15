package com.majlis.decision.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.majlis.decision.ai.AgentDef
import com.majlis.decision.ai.Agents
import com.majlis.decision.ui.components.InitialsAvatar
import com.majlis.decision.ui.components.SoftCard
import com.majlis.decision.ui.theme.Palette
import com.majlis.decision.ui.theme.Radii

/**
 * قائمة المحادثات — نقطة الدخول: غرفة القرار الجماعية أولاً، ثم كل
 * وكيل كجهة اتصال مستقلة يمكن محادثته وحده.
 */
@Composable
fun ChatListScreen(
    lastMessages: Map<String, String>,
    unread: Map<String, Int>,
    onOpen: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    LazyColumn(
        modifier = modifier.fillMaxWidth(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(
            start = 18.dp, end = 18.dp, bottom = 28.dp,
        ),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item {
            Text(
                "المحادثات",
                color = Palette.TextOnDark,
                fontSize = 42.sp,
                fontWeight = FontWeight.Normal,
                modifier = Modifier.padding(top = 4.dp, bottom = 10.dp),
            )
        }

        item {
            WarRoomCard(
                subtitle = lastMessages[Agents.WAR_ROOM]
                    ?: "المجلس كامل — ${Agents.SPECIALISTS.size} وكلاء + التنسيقي",
                badge = unread[Agents.WAR_ROOM] ?: 0,
                onClick = { onOpen(Agents.WAR_ROOM) },
            )
        }

        item {
            Text(
                "محادثة فردية",
                color = Palette.TextMutedOnDark,
                fontSize = 13.sp,
                modifier = Modifier.padding(top = 10.dp, bottom = 2.dp),
            )
        }

        items(Agents.ALL, key = { it.id }) { agent ->
            AgentRow(
                agent = agent,
                subtitle = lastMessages[agent.id] ?: agent.role,
                badge = unread[agent.id] ?: 0,
                onClick = { onOpen(agent.id) },
            )
        }
    }
}

@Composable
private fun WarRoomCard(subtitle: String, badge: Int, onClick: () -> Unit) {
    // غرفة القرار مميّزة بلون التمييز: هي الفعل الرئيسي في التطبيق
    SoftCard(modifier = Modifier.fillMaxWidth(), color = Palette.Accent, onClick = onClick) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                modifier = Modifier.size(50.dp).clip(CircleShape).background(Palette.CardDark),
                contentAlignment = Alignment.Center,
            ) {
                Text("قر", color = Palette.Accent, fontWeight = FontWeight.Bold, fontSize = 15.sp)
            }
            Spacer(Modifier.size(12.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    "غرفة القرار",
                    color = Palette.TextPrimary, fontSize = 18.sp, fontWeight = FontWeight.Bold,
                )
                Text(
                    subtitle,
                    color = Palette.TextPrimary.copy(alpha = 0.7f), fontSize = 12.sp,
                    maxLines = 1, overflow = TextOverflow.Ellipsis,
                )
            }
            if (badge > 0) UnreadBadge(badge, Palette.CardDark, Palette.Accent)
        }
    }
}

@Composable
private fun AgentRow(agent: AgentDef, subtitle: String, badge: Int, onClick: () -> Unit) {
    SoftCard(modifier = Modifier.fillMaxWidth(), color = Palette.CardLight, onClick = onClick) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            InitialsAvatar(agent.initials, agent.colorArgb, size = 46)
            Spacer(Modifier.size(12.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    agent.name,
                    color = Palette.TextPrimary, fontSize = 16.sp, fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                )
                Spacer(Modifier.height(2.dp))
                Text(
                    subtitle,
                    color = Palette.TextMuted, fontSize = 12.sp,
                    maxLines = 1, overflow = TextOverflow.Ellipsis,
                )
            }
            if (badge > 0) UnreadBadge(badge, Palette.CardDark, Palette.Accent)
        }
    }
}

@Composable
private fun UnreadBadge(
    count: Int,
    background: androidx.compose.ui.graphics.Color,
    content: androidx.compose.ui.graphics.Color,
) {
    Box(
        modifier = Modifier.clip(Radii.Pill).background(background)
            .padding(horizontal = 8.dp, vertical = 3.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text("$count", color = content, fontSize = 11.sp, fontWeight = FontWeight.Bold)
    }
}
