package com.majlis.decision.ui.screens

import androidx.compose.foundation.background
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.majlis.decision.data.Prefs
import com.majlis.decision.ui.theme.Palette
import com.majlis.decision.ui.theme.Radii

/**
 * إعدادات التطبيق.
 *
 * المفتاح مفتاحك أنت ويبقى على جهازك؛ لا يوجد مفتاح مضمّن في التطبيق،
 * ولا يُرسل إلى أي جهة سوى Anthropic. هذا مذكور في الشاشة نفسها لأن
 * المستخدم يستحق أن يعرف أين يذهب مفتاحه قبل أن يكتبه.
 */
@Composable
fun SettingsDialog(
    initialKey: String,
    initialModel: String,
    initialSearch: Boolean,
    onSave: (key: String, model: String, search: Boolean) -> Unit,
    onDismiss: () -> Unit,
) {
    var key by remember { mutableStateOf(initialKey) }
    var model by remember { mutableStateOf(initialModel) }
    var search by remember { mutableStateOf(initialSearch) }
    var reveal by remember { mutableStateOf(false) }

    Dialog(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(Radii.Card)
                .background(Palette.BackgroundDeep)
                .verticalScroll(rememberScrollState())
                .padding(20.dp),
        ) {
            Text("الإعدادات", color = Palette.TextOnDark, fontSize = 22.sp,
                fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(4.dp))
            Text(
                "التطبيق يتصل بالإنترنت ويبحث ويحلل بنفسه عبر Claude. " +
                    "يحتاج مفتاحك الخاص للعمل.",
                color = Palette.TextMutedOnDark, fontSize = 12.sp, lineHeight = 18.sp,
            )

            Spacer(Modifier.height(18.dp))
            Label("مفتاح Anthropic")
            TextField(
                value = key,
                onValueChange = { key = it },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                placeholder = { Text("sk-ant-...", color = Palette.TextMuted, fontSize = 13.sp) },
                textStyle = LocalTextStyle.current.copy(fontSize = 13.sp),
                visualTransformation = if (reveal) VisualTransformation.None
                else PasswordVisualTransformation(),
                shape = Radii.Small,
                colors = fieldColors(),
            )
            Spacer(Modifier.height(6.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier.clip(Radii.Pill).background(Palette.CardDark)
                        .clickable { reveal = !reveal }
                        .padding(horizontal = 12.dp, vertical = 6.dp)
                ) {
                    Text(
                        if (reveal) "إخفاء" else "إظهار",
                        color = Palette.TextOnDark, fontSize = 11.sp,
                    )
                }
                Spacer(Modifier.size(10.dp))
                Text(
                    "يُحفظ على جهازك فقط",
                    color = Palette.TextMutedOnDark, fontSize = 11.sp,
                )
            }
            Spacer(Modifier.height(6.dp))
            Text(
                "احصل عليه من console.anthropic.com ← API Keys. " +
                    "الاستخدام يُحتسب على حسابك أنت.",
                color = Palette.TextMutedOnDark, fontSize = 11.sp, lineHeight = 17.sp,
            )

            Spacer(Modifier.height(20.dp))
            Label("النموذج")
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Prefs.MODELS.forEach { (id, label) ->
                    ModelOption(
                        label = label,
                        selected = model == id,
                        onClick = { model = id },
                    )
                }
            }

            Spacer(Modifier.height(18.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text("البحث الحي على الإنترنت", color = Palette.TextOnDark, fontSize = 14.sp)
                    Text(
                        "يتحقق الوكلاء من الوقائع بمصادر حديثة",
                        color = Palette.TextMutedOnDark, fontSize = 11.sp,
                    )
                }
                Switch(
                    checked = search,
                    onCheckedChange = { search = it },
                    colors = SwitchDefaults.colors(
                        checkedThumbColor = Palette.TextPrimary,
                        checkedTrackColor = Palette.Accent,
                        uncheckedThumbColor = Palette.TextMutedOnDark,
                        uncheckedTrackColor = Palette.CardDark,
                    ),
                )
            }

            Spacer(Modifier.height(22.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Box(
                    modifier = Modifier.weight(1f).clip(Radii.Pill)
                        .background(Palette.CardDark).clickable { onDismiss() }
                        .padding(vertical = 13.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Text("إلغاء", color = Palette.TextOnDark, fontSize = 14.sp)
                }
                Box(
                    modifier = Modifier.weight(1.4f).clip(Radii.Pill)
                        .background(Palette.Accent)
                        .clickable { onSave(key.trim(), model, search) }
                        .padding(vertical = 13.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        "حفظ", color = Palette.TextPrimary, fontSize = 14.sp,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
        }
    }
}

@Composable
private fun Label(text: String) {
    Text(text, color = Palette.TextOnDark, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
    Spacer(Modifier.height(7.dp))
}

@Composable
private fun ModelOption(label: String, selected: Boolean, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(Radii.Small)
            .background(if (selected) Palette.Accent else Palette.CardDark)
            .clickable { onClick() }
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier.size(16.dp).clip(CircleShape)
                .background(if (selected) Palette.TextPrimary else Palette.TextMutedOnDark)
        )
        Spacer(Modifier.size(10.dp))
        Text(
            label,
            color = if (selected) Palette.TextPrimary else Palette.TextOnDark,
            fontSize = 13.sp,
            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
        )
    }
}

@Composable
private fun fieldColors() = TextFieldDefaults.colors(
    focusedContainerColor = Palette.CardWhite,
    unfocusedContainerColor = Palette.CardLight,
    focusedTextColor = Palette.TextPrimary,
    unfocusedTextColor = Palette.TextPrimary,
    focusedIndicatorColor = Color.Transparent,
    unfocusedIndicatorColor = Color.Transparent,
    cursorColor = Palette.TextPrimary,
)
