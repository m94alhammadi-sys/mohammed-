package com.majlis.decision.ui.components

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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.majlis.decision.ui.theme.Palette
import com.majlis.decision.ui.theme.Radii

/** بطاقة مستديرة — العنصر البنائي الأساسي في التصميم. */
@Composable
fun SoftCard(
    modifier: Modifier = Modifier,
    color: Color = Palette.CardLight,
    onClick: (() -> Unit)? = null,
    content: @Composable () -> Unit,
) {
    Box(
        modifier = modifier
            .clip(Radii.Card)
            .background(color)
            .then(if (onClick != null) Modifier.clickable { onClick() } else Modifier)
    ) { content() }
}

/** زر دائري شفاف — أزرار الرجوع والإعدادات في رأس الشاشة. */
@Composable
fun CircleButton(
    label: String,
    modifier: Modifier = Modifier,
    background: Color = Palette.CardLight,
    contentColor: Color = Palette.TextPrimary,
    size: Int = 44,
    onClick: () -> Unit = {},
) {
    Box(
        modifier = modifier
            .size(size.dp)
            .clip(CircleShape)
            .background(background)
            .clickable { onClick() },
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = contentColor, fontSize = 17.sp, fontWeight = FontWeight.Medium)
    }
}

/** كبسولة تنقّل أو تصفية. */
@Composable
fun PillButton(
    text: String,
    selected: Boolean = false,
    modifier: Modifier = Modifier,
    onClick: () -> Unit = {},
) {
    Box(
        modifier = modifier
            .clip(Radii.Pill)
            .background(if (selected) Palette.Accent else Palette.CardLight)
            .clickable { onClick() }
            .padding(horizontal = 18.dp, vertical = 11.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = text,
            color = Palette.TextPrimary,
            fontSize = 14.sp,
            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Medium,
            maxLines = 1,
        )
    }
}

/**
 * كبسولة إحصاء بأربعة أنماط، كما في صف المؤشرات بأعلى شاشة الصورة:
 * داكنة، ومميّزة بالأصفر، ومموّهة (مخطّطة)، ومحدّدة بإطار فقط.
 */
enum class StatStyle { Dark, Accent, Muted, Outlined }

@Composable
fun StatPill(
    label: String,
    value: String,
    style: StatStyle,
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier) {
        Text(
            text = label,
            color = Palette.TextOnDark.copy(alpha = 0.85f),
            fontSize = 11.sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Spacer(Modifier.height(6.dp))
        Box(
            modifier = Modifier
                .clip(Radii.Pill)
                .then(
                    when (style) {
                        StatStyle.Dark -> Modifier.background(Palette.CardDark)
                        StatStyle.Accent -> Modifier.background(Palette.Accent)
                        StatStyle.Muted -> Modifier.background(Palette.Background.copy(alpha = 0.55f))
                        StatStyle.Outlined -> Modifier.border(1.5.dp, Palette.CardLight, Radii.Pill)
                    }
                )
                .padding(horizontal = 16.dp, vertical = 10.dp),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = value,
                color = when (style) {
                    StatStyle.Dark -> Palette.TextOnDark
                    StatStyle.Accent -> Palette.TextPrimary
                    else -> Palette.TextOnDark
                },
                fontSize = 13.sp,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

/** شارة حالة صغيرة بنقطة ملوّنة. */
@Composable
fun StatusChip(
    text: String,
    dotColor: Color = Palette.ChipDot,
    background: Color = Palette.Chip,
    textColor: Color = Palette.TextPrimary,
) {
    Row(
        modifier = Modifier
            .clip(Radii.Pill)
            .background(background)
            .padding(horizontal = 12.dp, vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(7.dp).clip(CircleShape).background(dotColor))
        Spacer(Modifier.width(7.dp))
        Text(text, color = textColor, fontSize = 12.sp, fontWeight = FontWeight.Medium)
    }
}

/** صورة رمزية دائرية بالحروف الأولى. */
@Composable
fun InitialsAvatar(
    initials: String,
    argb: Long,
    size: Int = 46,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .size(size.dp)
            .clip(CircleShape)
            .background(Color(argb)),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = initials,
            color = Color.White,
            fontSize = (size / 3.4).sp,
            fontWeight = FontWeight.Bold,
        )
    }
}

/** عمود حقل: عنوان صغير فوق قيمة — كما في شبكة بطاقة الشخص. */
@Composable
fun FieldColumn(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
    valueColor: Color = Palette.TextPrimary,
) {
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(3.dp)) {
        Text(label, color = Palette.TextMuted, fontSize = 11.sp, maxLines = 1)
        Text(
            value,
            color = valueColor,
            fontSize = 14.sp,
            fontWeight = FontWeight.SemiBold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

/** فاصل منقّط أفقي، كما في بطاقة الجهاز السفلية في التصميم. */
@Composable
fun DottedDivider(modifier: Modifier = Modifier, color: Color = Palette.Outline) {
    Row(
        modifier = modifier.fillMaxWidth().height(2.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        repeat(44) {
            Box(Modifier.size(2.dp).clip(CircleShape).background(color))
        }
    }
}
