package com.majlis.decision.ui.components

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.majlis.decision.ui.theme.Palette

/**
 * مقياس قوسي كما في بطاقة «Security status» في التصميم المرجعي:
 * قوس علوي نصف دائري، الجزء المنجز بلون التمييز والباقي داكن،
 * والنسبة في المنتصف مع وصف تحتها.
 */
@Composable
fun ArcGauge(
    value: Double,
    caption: String,
    modifier: Modifier = Modifier,
    trackColor: Color = Palette.CardDark,
    progressColor: Color = Palette.Accent,
    valueColor: Color = Palette.TextPrimary,
    captionColor: Color = Palette.TextMuted,
) {
    val target = value.coerceIn(0.0, 1.0).toFloat()
    val animated by animateFloatAsState(
        targetValue = target,
        animationSpec = tween(durationMillis = 900),
        label = "gauge",
    )

    Box(modifier = modifier, contentAlignment = Alignment.Center) {
        Canvas(modifier = Modifier.fillMaxWidth().height(150.dp)) {
            val strokeWidth = 30.dp.toPx()
            val inset = strokeWidth / 2f
            val diameter = minOf(size.width - strokeWidth, (size.height - inset) * 2f)
            val arcSize = Size(diameter, diameter)
            val topLeft = Offset((size.width - diameter) / 2f, inset)

            // المسار الكامل (نصف دائرة من اليسار إلى اليمين)
            drawArc(
                color = trackColor,
                startAngle = 180f,
                sweepAngle = 180f,
                useCenter = false,
                topLeft = topLeft,
                size = arcSize,
                style = Stroke(width = strokeWidth, cap = androidx.compose.ui.graphics.StrokeCap.Round),
            )
            // الجزء المنجز
            drawArc(
                color = progressColor,
                startAngle = 180f,
                sweepAngle = 180f * animated,
                useCenter = false,
                topLeft = topLeft,
                size = arcSize,
                style = Stroke(width = strokeWidth, cap = androidx.compose.ui.graphics.StrokeCap.Round),
            )
        }

        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.padding(top = 46.dp),
        ) {
            Text(
                text = "${(target * 100).toInt()}%",
                color = valueColor,
                fontSize = 40.sp,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.height(2.dp))
            Text(caption, color = captionColor, fontSize = 13.sp)
        }
    }
}
