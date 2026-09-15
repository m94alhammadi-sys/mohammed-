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
import com.majlis.decision.data.SourceHealth
import com.majlis.decision.data.SourceSummary
import com.majlis.decision.ui.components.CircleButton
import com.majlis.decision.ui.components.DotWorldMap
import com.majlis.decision.ui.components.DottedDivider
import com.majlis.decision.ui.components.MapMarker
import com.majlis.decision.ui.components.SoftCard
import com.majlis.decision.ui.theme.Palette
import com.majlis.decision.ui.theme.Radii

/**
 * شاشة «المصادر» — نظير شاشة Devices في التصميم المرجعي:
 * بطاقتا ملخص بأعلى، ثم خريطة تغطية نقطية بأزرار تكبير، ثم بطاقة
 * تفصيل بيضاء بفاصل منقّط، ثم قائمة كل الموصلات.
 */
@Composable
fun SourcesScreen(
    summary: SourceSummary,
    sources: List<SourceHealth>,
    modifier: Modifier = Modifier,
) {
    val selected = sources.firstOrNull { it.ok } ?: sources.firstOrNull()

    LazyColumn(
        modifier = modifier.fillMaxWidth(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(
            start = 18.dp, end = 18.dp, bottom = 28.dp,
        ),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Text(
                text = "المصادر",
                color = Palette.TextOnDark,
                fontSize = 42.sp,
                fontWeight = FontWeight.Normal,
                modifier = Modifier.padding(top = 4.dp, bottom = 10.dp),
            )
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                SummaryTile("مصادر حية", "${summary.working} عنصراً", Palette.CardWhite, Modifier.weight(1f))
                SummaryTile("بانتظار مفاتيح", "${summary.needsKey} عنصراً", Palette.CardLight, Modifier.weight(1f))
            }
        }

        item { CoverageMap(sources) }

        if (selected != null) {
            item { SelectedSourceCard(selected) }
        }

        item {
            Text(
                text = "كل الموصلات",
                color = Palette.TextOnDark,
                fontSize = 15.sp,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(top = 8.dp, bottom = 2.dp),
            )
        }

        items(sources, key = { it.source + it.agent }) { SourceRow(it) }
    }
}

@Composable
private fun SummaryTile(title: String, subtitle: String, color: androidx.compose.ui.graphics.Color, modifier: Modifier) {
    SoftCard(modifier = modifier, color = color) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                modifier = Modifier
                    .size(42.dp)
                    .clip(Radii.Small)
                    .background(Palette.CardDark),
                contentAlignment = Alignment.Center,
            ) {
                Text("◈", color = Palette.Accent, fontSize = 18.sp)
            }
            Spacer(Modifier.size(10.dp))
            Column {
                Text(
                    title, color = Palette.TextPrimary, fontSize = 14.sp,
                    fontWeight = FontWeight.SemiBold, maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(subtitle, color = Palette.TextMuted, fontSize = 12.sp, maxLines = 1)
            }
        }
    }
}

@Composable
private fun CoverageMap(sources: List<SourceHealth>) {
    // توزيع تمثيلي للعلامات على الخريطة حسب عدد المصادر العاملة
    val working = sources.count { it.ok }
    val markers = listOf(
        MapMarker(0.24f, 0.42f, working),
        MapMarker(0.52f, 0.34f, sources.count { it.actionable }),
        MapMarker(0.33f, 0.70f, sources.size - working),
    ).filter { it.count > 0 }

    SoftCard(
        modifier = Modifier.fillMaxWidth(),
        color = Palette.BackgroundDeep,
    ) {
        Column(Modifier.padding(bottom = 14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "خريطة التغطية",
                    color = Palette.TextOnDark,
                    fontSize = 20.sp,
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier.weight(1f),
                )
                CircleButton("+", background = Palette.CardWhite, size = 38)
                Spacer(Modifier.size(8.dp))
                CircleButton("−", background = Palette.CardWhite, size = 38)
            }

            Box(Modifier.fillMaxWidth().height(180.dp)) {
                DotWorldMap(
                    markers = markers,
                    modifier = Modifier.fillMaxWidth().height(180.dp),
                )
            }

            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp),
                horizontalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                LegendDot(Palette.Accent, "عاملة $working")
                LegendDot(Palette.CardLight, "إجمالي ${sources.size}")
            }
        }
    }
}

@Composable
private fun LegendDot(color: androidx.compose.ui.graphics.Color, label: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(9.dp).clip(CircleShape).background(color))
        Spacer(Modifier.size(6.dp))
        Text(label, color = Palette.TextOnDark.copy(alpha = 0.85f), fontSize = 12.sp)
    }
}

@Composable
private fun SelectedSourceCard(source: SourceHealth) {
    SoftCard(modifier = Modifier.fillMaxWidth(), color = Palette.CardWhite) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier.size(48.dp).clip(Radii.Small).background(Palette.CardDark),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(if (source.ok) "✓" else "!", color = Palette.Accent, fontSize = 20.sp)
                }
                Spacer(Modifier.size(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        source.source, color = Palette.TextPrimary, fontSize = 17.sp,
                        fontWeight = FontWeight.SemiBold, maxLines = 1,
                    )
                    Text(source.state, color = Palette.TextMuted, fontSize = 13.sp, maxLines = 1)
                }
                Text("⋮", color = Palette.TextMuted, fontSize = 20.sp)
            }

            Spacer(Modifier.height(14.dp))
            DottedDivider()
            Spacer(Modifier.height(12.dp))

            Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(
                    source.detail.ifBlank { "—" },
                    color = Palette.TextPrimary, fontSize = 12.sp,
                    maxLines = 2, overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                Spacer(Modifier.size(10.dp))
                Text(
                    "${source.evidence} دليل",
                    color = Palette.TextMuted, fontSize = 12.sp, maxLines = 1,
                )
            }
        }
    }
}

@Composable
private fun SourceRow(source: SourceHealth) {
    SoftCard(
        modifier = Modifier.fillMaxWidth(),
        color = if (source.ok) Palette.CardLight else Palette.CardDark,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                modifier = Modifier
                    .size(34.dp)
                    .clip(CircleShape)
                    .background(
                        when {
                            source.ok -> Palette.Accent
                            source.actionable -> Palette.CardLight
                            else -> Palette.Danger.copy(alpha = 0.35f)
                        }
                    ),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    when {
                        source.ok -> "✓"
                        source.actionable -> "🔑"
                        else -> "⛔"
                    },
                    fontSize = 13.sp,
                    color = Palette.TextPrimary,
                )
            }
            Spacer(Modifier.size(11.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    source.source,
                    color = if (source.ok) Palette.TextPrimary else Palette.TextOnDark,
                    fontSize = 14.sp, fontWeight = FontWeight.SemiBold, maxLines = 1,
                )
                Text(
                    source.state,
                    color = if (source.ok) Palette.TextMuted else Palette.TextMutedOnDark,
                    fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                )
            }
            Text(
                source.agent,
                color = if (source.ok) Palette.TextMuted else Palette.TextMutedOnDark,
                fontSize = 11.sp, maxLines = 1,
            )
        }
    }
}
