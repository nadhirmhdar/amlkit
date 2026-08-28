package com.amlkit.mobile.ui.common

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.amlkit.mobile.ui.theme.AmlDanger
import com.amlkit.mobile.ui.theme.AmlDangerContainer
import com.amlkit.mobile.ui.theme.AmlSuccess
import com.amlkit.mobile.ui.theme.AmlSuccessContainer
import com.amlkit.mobile.ui.theme.AmlWarning
import com.amlkit.mobile.ui.theme.AmlWarningContainer

@Composable
fun FullScreenLoading(modifier: Modifier = Modifier) {
    Box(modifier = modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        CircularProgressIndicator()
    }
}

@Composable
fun ErrorBanner(message: String, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier.fillMaxWidth().padding(12.dp),
        shape = RoundedCornerShape(12.dp),
        color = AmlDangerContainer,
    ) {
        Text(
            text = message,
            color = AmlDanger,
            modifier = Modifier.padding(12.dp),
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

/** Small colored label used for alert/customer/report status everywhere --
 * category and severity vocabularies overlap across screens (sanction /
 * terrorism / proliferation / high / breach / true_positive / ...), so this
 * takes freeform text and a tone rather than an enum tied to one screen. */
enum class PillTone { DANGER, WARNING, SUCCESS, NEUTRAL }

@Composable
fun StatusPill(text: String, tone: PillTone, modifier: Modifier = Modifier) {
    val (bg, fg) = when (tone) {
        PillTone.DANGER -> AmlDangerContainer to AmlDanger
        PillTone.WARNING -> AmlWarningContainer to AmlWarning
        PillTone.SUCCESS -> AmlSuccessContainer to AmlSuccess
        PillTone.NEUTRAL -> MaterialTheme.colorScheme.surfaceVariant to MaterialTheme.colorScheme.onSurfaceVariant
    }
    Surface(shape = RoundedCornerShape(50), color = bg, modifier = modifier) {
        Text(
            text = text,
            color = fg,
            style = MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
        )
    }
}

fun categoryTone(category: String): PillTone = when (category) {
    "sanction", "terrorism", "proliferation" -> PillTone.DANGER
    "pep" -> PillTone.WARNING
    else -> PillTone.NEUTRAL
}

fun alertStatusTone(status: String): PillTone = when (status) {
    "open" -> PillTone.WARNING
    "pending_review" -> PillTone.WARNING
    "true_positive", "escalated" -> PillTone.DANGER
    "false_positive" -> PillTone.SUCCESS
    else -> PillTone.NEUTRAL
}

fun riskTone(rating: String?): PillTone = when (rating) {
    "high" -> PillTone.DANGER
    "medium" -> PillTone.WARNING
    "low" -> PillTone.SUCCESS
    else -> PillTone.NEUTRAL
}

@Composable
fun SectionCard(
    title: String,
    modifier: Modifier = Modifier,
    content: @Composable ColumnScopeAlias.() -> Unit,
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(text = title, style = MaterialTheme.typography.titleMedium)
            content()
        }
    }
}

/** Alias so SectionCard's content lambda can be typed against Column's scope
 * without importing ColumnScope at every call site. */
typealias ColumnScopeAlias = androidx.compose.foundation.layout.ColumnScope

val screenContentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp)
