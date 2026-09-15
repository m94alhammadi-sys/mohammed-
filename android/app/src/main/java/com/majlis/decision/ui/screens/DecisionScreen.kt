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
import com.majlis.decision.data.DecisionSummary
import com.majlis.decision.data.SessionEntry
import com.majlis.decision.data.SessionKind
import com.majlis.decision.ui.components.ArcGauge
import com.majlis.decision.ui.components.InitialsAvatar
import com.majlis.decision.ui.components.SoftCard
import com.majlis.decision.ui.theme.Palette
import com.majlis.decision.ui.theme.Radii

/**
 * شاشة «القرار» — نظير شاشة Security status في التصميم المرجعي:
 * بطاقة فاتحة بمقياس قوسي كبير، ثم بطاقة داكنة بسجل التقارير.
 */
@Composable
fun DecisionScreen(
    decision: DecisionSummary,
    sessions: List<SessionEntry>,
    modifier: Modifier = Modifier,
) {
    LazyColumn(
        modifier = modifier.fillMaxWidth(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(
            start = 18.dp, end = 18.dp, bottom = 28.dp,
        ),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Text(
                text = "القرار",
                color = Palette.TextOnDark,
                fontSize = 42.sp,
                fontWeight = FontWeight.Normal,
                modifier = Modifier.padding(top = 4.dp, bottom = 10.dp),
            )
        }

        item { ConfidenceCard(decision) }
        item { RecommendationCard(decision) }
        item { SessionHistoryCard(sessions) }
    }
}

@Composable
private fun ConfidenceCard(decision: DecisionSummary) {
    SoftCard(modifier = Modifier.fillMaxWidth(), color = Palette.CardLight) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(vertical = 20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                "ثقة القرار",
                color = Palette.TextPrimary,
                fontSize = 24.sp,
                fontWeight = FontWeight.Medium,
            )
            Spacer(Modifier.height(6.dp))
            ArcGauge(
                value = decision.confidence,
                caption = riskLabel(decision.risk),
                modifier = Modifier.fillMaxWidth().height(150.dp),
            )
            Spacer(Modifier.height(10.dp))
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                MiniStat("الاتجاه", decision.stance)
                MiniStat("التضارب", "${decision.conflicts}")
                MiniStat("المصادر", "${decision.sources}")
                MiniStat("المخاطرة", "${(decision.risk * 100).toInt()}%")
            }
        }
    }
}

@Composable
private fun MiniStat(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, color = Palette.TextPrimary, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
        Text(label, color = Palette.TextMuted, fontSize = 11.sp)
    }
}

@Composable
private fun RecommendationCard(decision: DecisionSummary) {
    SoftCard(modifier = Modifier.fillMaxWidth(), color = Palette.CardWhite) {
        Column(Modifier.padding(16.dp)) {
            Text(
                decision.topic.ifBlank { "—" },
                color = Palette.TextMuted, fontSize = 12.sp,
                maxLines = 2, overflow = TextOverflow.Ellipsis,
            )
            Spacer(Modifier.height(8.dp))
            Text(
                decision.recommendation.ifBlank { "لا توصية" },
                color = Palette.TextPrimary, fontSize = 15.sp,
                fontWeight = FontWeight.Medium, lineHeight = 22.sp,
            )
            if (decision.qualityFlags.isNotEmpty()) {
                Spacer(Modifier.height(12.dp))
                decision.qualityFlags.take(3).forEach { flag ->
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp),
                        verticalAlignment = Alignment.Top,
                    ) {
                        Text("⚠", color = Palette.Danger, fontSize = 12.sp)
                        Spacer(Modifier.size(6.dp))
                        Text(
                            flag.removePrefix("⚠ ").trim(),
                            color = Palette.TextMuted, fontSize = 12.sp, lineHeight = 17.sp,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun SessionHistoryCard(sessions: List<SessionEntry>) {
    SoftCard(modifier = Modifier.fillMaxWidth(), color = Palette.CardDark) {
        Column(Modifier.padding(vertical = 16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "سجل التقارير",
                    color = Palette.TextOnDark, fontSize = 20.sp,
                    fontWeight = FontWeight.Medium, modifier = Modifier.weight(1f),
                )
                Text(
                    "${sessions.count { it.kind == SessionKind.DECISION }}/${sessions.size}",
                    color = Palette.TextOnDark, fontSize = 20.sp, fontWeight = FontWeight.Light,
                )
            }
            Spacer(Modifier.height(10.dp))
            sessions.forEach { SessionRow(it) }
        }
    }
}

@Composable
private fun SessionRow(entry: SessionEntry) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // أيقونة نوع السجل داخل دائرة فاتحة، كما في التصميم المرجعي
        Box(
            modifier = Modifier.size(36.dp).clip(CircleShape).background(Palette.CardLight),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                when (entry.kind) {
                    SessionKind.REPORT -> "▤"
                    SessionKind.DECISION -> "◆"
                    SessionKind.ALERT -> "!"
                },
                color = Palette.TextPrimary, fontSize = 14.sp,
            )
        }
        Spacer(Modifier.size((-8).dp.coerceAtLeast(0.dp)))
        InitialsAvatar(entry.initials, entry.accentArgb, size = 38, modifier = Modifier.padding(start = 6.dp))
        Spacer(Modifier.size(10.dp))
        Column(Modifier.weight(1f)) {
            Text(
                entry.agentName, color = Palette.TextOnDark, fontSize = 14.sp,
                fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis,
            )
            Text(entry.timestamp, color = Palette.TextMutedOnDark, fontSize = 12.sp, maxLines = 1)
        }
        Column(horizontalAlignment = Alignment.End) {
            Text(
                "${(entry.confidence * 100).toInt()}%",
                color = if (entry.confidence < 0.4) Palette.Danger else Palette.Accent,
                fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
            )
            Text(entry.place, color = Palette.TextMutedOnDark, fontSize = 11.sp, maxLines = 1)
        }
    }
}

private fun riskLabel(risk: Double): String = when {
    risk >= 0.66 -> "مخاطرة مرتفعة"
    risk >= 0.33 -> "مخاطرة متوسطة"
    else -> "مخاطرة منخفضة"
}
