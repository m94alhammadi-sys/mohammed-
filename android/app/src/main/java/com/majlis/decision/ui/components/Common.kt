package com.majlis.decision.ui.components

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
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

/** زر دائري — الرجوع والإعدادات في رأس الشاشة. */
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

/**
 * مقياس قوسي — العنصر المميّز في التصميم المرجعي («Security status»).
 * يظهر هنا داخل فقاعة القرار حيث يحمل معنى: ثقة الوكيل التنسيقي.
 */
@Composable
fun ArcGauge(
    value: Double,
    caption: String,
    modifier: Modifier = Modifier,
    trackColor: Color = Palette.CardDark,
    progressColor: Color = Palette.Accent,
) {
    val target = value.coerceIn(0.0, 1.0).toFloat()
    val animated by animateFloatAsState(
        targetValue = target,
        animationSpec = tween(durationMillis = 800),
        label = "gauge",
    )

    Box(modifier = modifier, contentAlignment = Alignment.Center) {
        Canvas(modifier = Modifier.fillMaxWidth().height(96.dp)) {
            val strokeWidth = 20.dp.toPx()
            val inset = strokeWidth / 2f
            val diameter = minOf(size.width - strokeWidth, (size.height - inset) * 2f)
            val arcSize = Size(diameter, diameter)
            val topLeft = Offset((size.width - diameter) / 2f, inset)

            drawArc(
                color = trackColor, startAngle = 180f, sweepAngle = 180f, useCenter = false,
                topLeft = topLeft, size = arcSize,
                style = Stroke(width = strokeWidth, cap = StrokeCap.Round),
            )
            drawArc(
                color = progressColor, startAngle = 180f, sweepAngle = 180f * animated,
                useCenter = false, topLeft = topLeft, size = arcSize,
                style = Stroke(width = strokeWidth, cap = StrokeCap.Round),
            )
        }

        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.padding(top = 30.dp),
        ) {
            Text(
                "${(target * 100).toInt()}%",
                color = Palette.TextPrimary, fontSize = 26.sp, fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.height(1.dp))
            Text(caption, color = Palette.TextMuted, fontSize = 11.sp)
        }
    }
}
