package com.majlis.decision.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.majlis.decision.data.Agent
import com.majlis.decision.ui.components.FieldColumn
import com.majlis.decision.ui.components.InitialsAvatar
import com.majlis.decision.ui.components.SoftCard
import com.majlis.decision.ui.components.StatPill
import com.majlis.decision.ui.components.StatStyle
import com.majlis.decision.ui.components.StatusChip
import com.majlis.decision.ui.theme.Palette

/**
 * شاشة «الوكلاء» — نظير شاشة People في التصميم المرجعي:
 * صف مؤشرات كبسولية بأربعة أنماط، ثم بطاقات لكل وكيل بصورة رمزية
 * وشارة حالة وشبكة حقول ومربع اختيار.
 */
@Composable
fun AgentsScreen(
    agents: List<Agent>,
    selected: Set<String>,
    onToggle: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val live = agents.count { !it.degraded }
    val avgConfidence = if (agents.isEmpty()) 0.0 else agents.sumOf { it.confidence } / agents.size
    val degraded = agents.count { it.degraded }

    LazyColumn(
        modifier = modifier.fillMaxWidth(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(
            start = 18.dp, end = 18.dp, bottom = 28.dp,
        ),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Text(
                text = "الوكلاء",
                color = Palette.TextOnDark,
                fontSize = 42.sp,
                fontWeight = FontWeight.Normal,
                modifier = Modifier.padding(top = 4.dp, bottom = 14.dp),
            )
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                StatPill("وكلاء", "$live", StatStyle.Dark, Modifier.weight(1f))
                StatPill("متوسط الثقة", "${(avgConfidence * 100).toInt()}%", StatStyle.Accent, Modifier.weight(1.2f))
                StatPill("ناقص", "$degraded", StatStyle.Muted, Modifier.weight(0.9f))
                StatPill("مصادر", "${agents.size * 2}", StatStyle.Outlined, Modifier.weight(1f))
            }
        }

        items(agents, key = { it.id }) { agent ->
            AgentCard(
                agent = agent,
                checked = agent.id in selected,
                onToggle = { onToggle(agent.id) },
            )
        }
    }
}

@Composable
private fun AgentCard(agent: Agent, checked: Boolean, onToggle: () -> Unit) {
    // البطاقة المحددة تصبح بيضاء ناصعة، كما في التصميم المرجعي
    SoftCard(
        modifier = Modifier.fillMaxWidth(),
        color = if (checked) Palette.CardWhite else Palette.CardLight,
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                InitialsAvatar(agent.initials, agent.accentArgb)
                Spacer(Modifier.size(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        agent.name,
                        color = Palette.TextPrimary,
                        fontSize = 17.sp,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(agent.role, color = Palette.TextMuted, fontSize = 13.sp, maxLines = 1)
                }
                StatusChip(
                    text = agent.status,
                    dotColor = if (agent.degraded) Palette.Danger else Palette.ChipDot,
                    background = if (agent.degraded) Palette.Danger.copy(alpha = 0.16f) else Palette.Chip,
                )
            }

            Spacer(Modifier.height(16.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                FieldColumn("التخصص", agent.specialty, Modifier.weight(1.1f))
                FieldColumn("المصادر", agent.sources, Modifier.weight(1f))
                FieldColumn(
                    "الثقة",
                    "${(agent.confidence * 100).toInt()}%",
                    Modifier.weight(0.7f),
                    valueColor = if (agent.confidence < 0.4) Palette.Danger else Palette.TextPrimary,
                )
            }

            Spacer(Modifier.height(16.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("آخر تقرير", color = Palette.TextMuted, fontSize = 12.sp)
                Spacer(Modifier.size(10.dp))
                Text(
                    agent.lastReport,
                    color = Palette.TextPrimary,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier.weight(1f),
                )
                CheckBox(checked = checked, onToggle = onToggle)
            }
        }
    }
}

/** مربع اختيار مربّع الزوايا كما في التصميم (ليس دائرياً). */
@Composable
private fun CheckBox(checked: Boolean, onToggle: () -> Unit) {
    Box(
        modifier = Modifier
            .size(26.dp)
            .clip(RoundedCornerShape(8.dp))
            .then(
                if (checked) Modifier.background(Palette.TextPrimary)
                else Modifier.border(1.5.dp, Palette.Outline, RoundedCornerShape(8.dp))
            )
            .clickable { onToggle() },
        contentAlignment = Alignment.Center,
    ) {
        if (checked) {
            Text("✓", color = Palette.CardWhite, fontSize = 15.sp, fontWeight = FontWeight.Bold)
        }
    }
}
