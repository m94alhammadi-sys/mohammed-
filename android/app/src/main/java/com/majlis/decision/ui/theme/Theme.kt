package com.majlis.decision.ui.theme

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * لوحة الألوان مستخرجة من تصميم الصورة المرجعية:
 * خلفية رمادية فحمية، بطاقات فاتحة وبيضاء وداكنة، ولون تمييز أصفر ليموني.
 */
object Palette {
    val Background = Color(0xFF6E7478)      // جسم الشاشة الرمادي
    val BackgroundDeep = Color(0xFF63696D)  // تدرّج أغمق للعمق
    val CardLight = Color(0xFFE4E7E9)       // البطاقة الفاتحة الافتراضية
    val CardWhite = Color(0xFFFFFFFF)       // البطاقة المحددة/النشطة
    val CardDark = Color(0xFF23272B)        // البطاقة الداكنة (السجل)
    val Accent = Color(0xFFEDFF00)          // الأصفر الليموني المميِّز
    val AccentDim = Color(0xFFCBD900)
    val Chip = Color(0xFFD9F2C4)            // شارة الحالة الخضراء الفاتحة
    val ChipDot = Color(0xFF4CAF50)
    val TextPrimary = Color(0xFF14181B)
    val TextOnDark = Color(0xFFF2F4F5)
    val TextMuted = Color(0xFF6B7176)
    val TextMutedOnDark = Color(0xFF9AA1A6)
    val Outline = Color(0xFFB9BFC3)
    val Danger = Color(0xFFE05C5C)
}

/** أنصاف أقطار التصميم: بطاقات شديدة الاستدارة وأزرار كبسولية. */
object Radii {
    val Card = RoundedCornerShape(26.dp)
    val CardInner = RoundedCornerShape(20.dp)
    val Pill = RoundedCornerShape(percent = 50)
    val Small = RoundedCornerShape(14.dp)
}

private val MajlisTypography = Typography(
    // العناوين الكبيرة في التصميم خفيفة الوزن وواسعة
    displayLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Normal,
        fontSize = 42.sp,
        lineHeight = 48.sp,
        letterSpacing = (-0.5).sp,
    ),
    titleLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 20.sp,
        lineHeight = 26.sp,
    ),
    titleMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 16.sp,
        lineHeight = 22.sp,
    ),
    bodyMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Normal,
        fontSize = 14.sp,
        lineHeight = 20.sp,
    ),
    bodySmall = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Normal,
        fontSize = 12.sp,
        lineHeight = 16.sp,
    ),
    labelSmall = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Medium,
        fontSize = 11.sp,
        lineHeight = 14.sp,
    ),
)

@Composable
fun MajlisTheme(content: @Composable () -> Unit) {
    // التصميم أحادي النمط عمداً: الخلفية الفحمية جزء من هويته،
    // فلا يتبع نمط النظام الفاتح/الداكن.
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = Palette.Accent,
            onPrimary = Palette.TextPrimary,
            background = Palette.Background,
            onBackground = Palette.TextOnDark,
            surface = Palette.CardLight,
            onSurface = Palette.TextPrimary,
            error = Palette.Danger,
        ),
        typography = MajlisTypography,
        content = content,
    )
}
